#!/usr/bin/env python3
"""Void & Draconic Dashboard – Datensammler (Dauerdienst mc-dashboard.service).

Schreibt JSON-Dateien nach /var/www/mc-dashboard/data, die die Dashboard-Seite abholt:
  live.json     alle 2 s: Online-Status, Spieler, TPS je Dimension, CPU, RAM + Echtzeit-Verlauf (10 Min.)
  status.json   alle 30 s: System, Welt (Uhrzeit, Wetter, Mobs, Vorgenerierung, Größe), Backups, Ereignisse
  history.json  jede Minute: 24 h minütlich, 7 Tage in 10-Minuten-Schritten
  players.json  jede Minute: Statistiken pro Spieler (world/stats, world/advancements)
Außerdem schreibt er Zeile 2 der Server-Beschreibung (MiniMOTD) live.

Nur Python-Standardbibliothek. RCON nur über 127.0.0.1 (Port 25575 ist per ufw gesperrt),
eine dauerhafte Verbindung, damit das Server-Log nicht bei jeder Abfrage eine Zeile bekommt.
"""
import glob, gzip, json, os, re, socket, struct, subprocess, sys, time

MC = "/opt/void-draconic"
OUT = "/var/www/mc-dashboard/data"
STATE = "/var/lib/mc-dashboard"
HIST = os.path.join(STATE, "history.jsonl")
CACHE = os.path.join(STATE, "cache.json")
ADDRESS = "mc-void-draconic.duckdns.org"
LIVE_EVERY, SLOW_EVERY, MIN_EVERY = 2, 30, 60
DIM_NAMES = {"Overworld": "minecraft:overworld", "The Nether": "minecraft:the_nether", "The End": "minecraft:the_end"}


def write_json(name, data):
    tmp = os.path.join(OUT, "." + name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(OUT, name))


def sh(*cmd, timeout=20):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def props():
    p = {}
    try:
        for line in open(os.path.join(MC, "server.properties"), encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                p[k] = v
    except OSError:
        pass
    return p


def num(s):
    return float(s.replace(",", "."))


# ---------- Minecraft: Server List Ping ----------
def varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def read_varint(sock):
    n = shift = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise OSError("closed")
        n |= (b[0] & 0x7F) << shift
        if not b[0] & 0x80:
            return n
        shift += 7


def ping(port):
    with socket.create_connection(("127.0.0.1", port), timeout=4) as s:
        host = b"localhost"
        hs = varint(0) + varint(767) + varint(len(host)) + host + struct.pack(">H", port) + varint(1)
        s.sendall(varint(len(hs)) + hs + b"\x01\x00")
        read_varint(s), read_varint(s)
        size = read_varint(s)
        data = b""
        while len(data) < size:
            chunk = s.recv(size - len(data))
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode("utf-8"))


def plain(desc):
    if isinstance(desc, str):
        return re.sub("§.", "", desc)
    if isinstance(desc, list):
        return "".join(plain(d) for d in desc)
    if isinstance(desc, dict):
        return plain(desc.get("text", "")) + "".join(plain(e) for e in desc.get("extra", []))
    return ""


# ---------- RCON mit dauerhafter Verbindung ----------
class Rcon:
    def __init__(self):
        self.s, self.rid = None, 10

    def _recv(self):
        hdr = b""
        while len(hdr) < 4:
            c = self.s.recv(4 - len(hdr))
            if not c:
                raise OSError("closed")
            hdr += c
        ln = struct.unpack("<i", hdr)[0]
        d = b""
        while len(d) < ln:
            c = self.s.recv(ln - len(d))
            if not c:
                raise OSError("closed")
            d += c
        rid, typ = struct.unpack("<ii", d[:8])
        return rid, d[8:-2].decode("utf-8", "replace")

    def _send(self, rid, typ, body):
        b = body.encode("utf-8")
        self.s.sendall(struct.pack("<iii", len(b) + 10, rid, typ) + b + b"\x00\x00")

    def connect(self):
        p = props()
        if p.get("enable-rcon") != "true" or not p.get("rcon.password"):
            return False
        try:
            self.s = socket.create_connection(("127.0.0.1", int(p.get("rcon.port", 25575))), timeout=4)
            self._send(1, 3, p["rcon.password"])
            if self._recv()[0] == -1:
                self.close()
                return False
            return True
        except Exception:
            self.close()
            return False

    def close(self):
        try:
            self.s and self.s.close()
        except Exception:
            pass
        self.s = None

    def cmd(self, command):
        for _ in range(2):
            if not self.s and not self.connect():
                return None
            try:
                self.rid += 1
                self._send(self.rid, 2, command)
                # Endmarke: ungültiger Pakettyp liefert eine Antwort mit eigener ID -> lange Ausgaben vollständig lesen
                self._send(self.rid + 100000, 0, "")
                parts = []
                while True:
                    rid, body = self._recv()
                    if rid == self.rid + 100000:
                        break
                    parts.append(body)
                return re.sub("§.", "", "".join(parts))
            except Exception:
                self.close()
        return None


RCON = Rcon()


def parse_tps(text):
    """'Overworld: 20,000 TPS (0,443 ms/tick)' … 'Overall: …' (deutsches Dezimalkomma möglich)."""
    if not text:
        return None
    res = {"dims": {}}
    for m in re.finditer(r"([^\n:]+(?::[a-z0-9_/.-]+)?):\s*([\d.,]+)\s*TPS\s*\(([\d.,]+)\s*ms/tick\)", text):
        name, tps, ms = m.group(1).strip(), num(m.group(2)), num(m.group(3))
        if name == "Overall":
            res["tps"], res["mspt"] = tps, ms
        else:
            res["dims"][DIM_NAMES.get(name, name)] = {"name": name, "tps": tps, "mspt": ms}
    return res if "tps" in res else None


def entities(dim):
    out = RCON.cmd(f"execute in {dim} run neoforge entity list")
    if not out:
        return None
    m = re.search(r"Total:\s*(\d+)", out)
    top = [[name.split(":")[-1], int(n)] for n, name in re.findall(r"(\d+):\s*([a-z0-9_.-]+:[a-z0-9_/.-]+)", out)]
    return {"total": int(m.group(1)) if m else sum(n for _, n in top), "top": top[:6]}


def game_time():
    d, t = RCON.cmd("time query day"), RCON.cmd("time query daytime")
    md, mt = re.search(r"(\d+)", d or ""), re.search(r"(\d+)", t or "")
    if not mt:
        return None
    ticks = int(mt.group(1)) % 24000
    minutes = int(((ticks / 1000 + 6) % 24) * 60)
    return {"ticks": ticks, "day": int(md.group(1)) if md else None, "clock": f"{minutes // 60:02d}:{minutes % 60:02d}",
            "night": 12542 <= ticks <= 23460}


def weather(level):
    try:
        raw = gzip.open(os.path.join(MC, level, "level.dat")).read()
    except OSError:
        return None

    def flag(name):
        k = b"\x01" + struct.pack(">H", len(name)) + name
        i = raw.find(k)
        return bool(raw[i + len(k)]) if i >= 0 else False
    return "thunder" if flag(b"thundering") else "rain" if flag(b"raining") else "clear"


# ---------- System ----------
class Cpu:
    def __init__(self):
        self.last = self.snap()

    @staticmethod
    def snap():
        v = list(map(int, open("/proc/stat").readline().split()[1:]))
        return sum(v), v[3] + v[4]

    def percent(self):
        t, i = self.snap()
        lt, li = self.last
        self.last = (t, i)
        return round(100 * (1 - (i - li) / max(1, t - lt)), 1)


def meminfo():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":")
        m[k] = int(v.split()[0]) * 1024
    return m


def java_pid():
    out = sh("pgrep", "-u", "minecraft", "-f", "java.*nogui")
    return int(out.split()[0]) if out else None


def proc_rss(pid):
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None


def service_since(unit):
    v = sh("systemctl", "show", unit, "-p", "ActiveEnterTimestamp", "--value", "--timestamp=unix")
    return int(v.lstrip("@")) if v.startswith("@") else None


# ---------- Log: Vorgenerierung und Ereignisse ----------
DEATH = re.compile(r"\b(was slain|was shot|was killed|was blown up|blew up|died|drowned|fell|hit the ground|burned|went up in flames|"
                   r"tried to swim in lava|starved|suffocated|froze|withered|was pricked|was squashed|was impaled|was fireballed|"
                   r"experienced kinetic energy|was struck by lightning|was obliterated|discovered the floor was lava)\b")


def read_log_tail(n=3_000_000):
    path = os.path.join(MC, "logs", "latest.log")
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def chunky_progress(text):
    res = {}
    for m in re.finditer(r"\[Chunky\] Task (running|finished|stopped|paused) for ([a-z0-9_:]+)\.?(?: Processed: (\d+) chunks \(([\d.,]+)%\))?(?:, ETA: ([\d:]+))?(?:, Rate: ([\d.,]+) cps)?(?:, Total time: ([\d:]+))?", text):
        st, dim, n, pct, eta, rate, total = m.groups()
        cur = res.setdefault(dim, {})
        cur["state"] = st
        if n:
            cur["chunks"] = int(n)
        if pct:
            cur["percent"] = num(pct)
        if eta:
            cur["eta"] = eta
        if rate:
            cur["rate"] = num(rate)
        if total:
            cur["total_time"] = total
        if st == "finished":
            cur["percent"] = 100.0
    return res


def events(text, names):
    if not names:
        return []
    who = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    rx = re.compile(r"^\[(\d\d)(\w+)\.(\d{4}) (\d\d:\d\d):\d\d\.\d+\] \[Server thread/INFO\] \[net\.minecraft\.server\.MinecraftServer/\]: "
                    rf"(?:\[Not Secure\] )?({who})\b (.*)$", re.M | re.I)
    out = []
    for m in rx.finditer(text):
        name, rest = m.group(5), m.group(6).strip()
        if rest.startswith("joined the game"):
            kind, msg = "join", "ist beigetreten"
        elif rest.startswith("left the game"):
            kind, msg = "leave", "hat das Spiel verlassen"
        elif rest.startswith(("has made the advancement", "has completed the challenge", "has reached the goal")):
            kind, msg = "adv", "Fortschritt: " + re.sub(r"^has (made the advancement|completed the challenge|reached the goal)\s*", "", rest).strip("[] ")
        elif DEATH.search(rest) and not rest.startswith(("issued server command", "lost connection")):
            kind, msg = "death", rest
        else:
            continue
        out.append({"time": f"{m.group(1)}. {m.group(4)}", "name": name, "kind": kind, "msg": msg[:120]})
    return out[-25:][::-1]


# ---------- Welt ----------
def dir_size(path):
    out = sh("du", "-sb", path, timeout=120)
    return int(out.split()[0]) if out else None


def backups():
    """Lokal liegen nur Backups, die noch auf den Upload warten. mc-backup-cloud lädt jedes fertige Backup nach
    Google Drive, prüft Größe und MD5 dort und löscht es dann auf dem Server; seinen Stand liest diese Funktion."""
    files = []
    for f in glob.glob(os.path.join(MC, "simplebackups", "**", "*.zip"), recursive=True):
        st = os.stat(f)
        files.append({"name": os.path.basename(f), "size": st.st_size, "time": int(st.st_mtime)})
    files.sort(key=lambda x: x["time"], reverse=True)
    show = lambda u, p: sh("systemctl", "show", u, "-p", p, "--value", "--timestamp=unix")
    nxt = sh("date", "-d", show("mc-backup-cloud.timer", "NextElapseUSecRealtime"), "+@%s")
    try:
        sync = json.load(open("/var/lib/mc-dashboard/backup-sync.json", encoding="utf-8"))
    except (OSError, ValueError):
        sync = {}
    cloud = sync.get("cloud") or {}
    for x in cloud.get("files", []):
        if isinstance(x.get("time"), str):
            x["time"] = int(sh("date", "-d", x["time"], "+%s") or 0)
    return {"local": files[:5], "local_count": len(files), "local_size": sum(f["size"] for f in files),
            "cloud": {"last_upload": sync.get("last_upload"), "last_check": sync.get("last_run"),
                      "errors": sync.get("errors", []), "count": cloud.get("count"), "size": cloud.get("size"),
                      "files": cloud.get("files", []), "next_daily": int(nxt.lstrip("@")) if nxt.startswith("@") else None,
                      "running": sh("systemctl", "is-active", "mc-backup-sync.service") == "activating",
                      "target": "Minecraft Modpack - Void & Draconic/Backups"}}


# ---------- Laufendes Backup (live, alle 2 s) ----------
SYNC_STATE = "/var/lib/mc-dashboard/backup-sync.json"
_creating = {}  # ZIP -> (zuerst gesehen, Größe da)


def backup_live(now):
    """Was gerade passiert: Simple Backups schreibt eine ZIP (erstellen) und/oder mc-backup-cloud prüft/lädt hoch.
    Dazu der letzte fertige Stand. ETA beim Erstellen über die Größe des letzten Backups geschätzt."""
    try:
        sync = json.load(open(SYNC_STATE, encoding="utf-8"))
    except (OSError, ValueError):
        sync = {}
    last = sync.get("last_upload") or {}
    cloud = (sync.get("cloud") or {}).get("files") or []
    expected = last.get("size") or max([x.get("size", 0) for x in cloud] or [0])
    active = []
    seen = set()
    for f in glob.glob(os.path.join(MC, "simplebackups", "**", "*.zip"), recursive=True):
        try:
            st = os.stat(f)
        except OSError:
            continue
        if now - st.st_mtime > 15:
            continue
        seen.add(f)
        t0, s0 = _creating.setdefault(f, (now, st.st_size))
        speed = (st.st_size - s0) / (now - t0) if now - t0 >= 4 else 0
        total = max(expected, st.st_size)
        active.append({"phase": "erstellen", "file": os.path.basename(f), "done": st.st_size, "total": total,
                       "speed": speed, "eta": (total - st.st_size) / speed if speed > 0 else None, "started": int(t0), "estimated": True})
    for f in list(_creating):
        if f not in seen:
            del _creating[f]
    a = sync.get("active")
    if a and now - a.get("updated", 0) < 60:
        a = dict(a)
        if a.get("eta") is None and a.get("speed"):
            a["eta"] = max(0, (a.get("total", 0) - a.get("done", 0)) / a["speed"])
        active.append(a)
    return {"active": active, "last": last or None, "errors": sync.get("errors") or []}


# ---------- Spieler ----------
CUSTOM = {"play_time": "minecraft:play_time", "deaths": "minecraft:deaths", "mob_kills": "minecraft:mob_kills",
          "player_kills": "minecraft:player_kills", "jumps": "minecraft:jump", "damage_dealt": "minecraft:damage_dealt",
          "damage_taken": "minecraft:damage_taken", "sleep": "minecraft:sleep_in_bed", "leave_game": "minecraft:leave_game"}
DIST = {"walk": ["walk_one_cm", "sprint_one_cm", "crouch_one_cm", "walk_on_water_one_cm", "walk_under_water_one_cm"],
        "fly": ["fly_one_cm", "aviate_one_cm"], "swim": ["swim_one_cm"],
        "ride": ["boat_one_cm", "horse_one_cm", "minecart_one_cm", "pig_one_cm", "strider_one_cm"],
        "climb": ["climb_one_cm"], "fall": ["fall_one_cm"]}


def known_names():
    names, wl = {}, []
    for fn in ("usercache.json", "whitelist.json"):
        try:
            for e in json.load(open(os.path.join(MC, fn), encoding="utf-8")):
                names[e["uuid"]] = e["name"]
                if fn == "whitelist.json":
                    wl.append(e["uuid"])
        except (OSError, ValueError):
            pass
    return names, wl


# ---------- Skins (für die Spielerköpfe im Dashboard) ----------
SKINS = os.path.join(OUT, "skins")
SKIN_EVERY = 6 * 3600  # Skin-Wechsel kommen nach spätestens 6 Stunden an


def fetch_skin(uuid):
    """Lädt den Skin über den Mojang-Sessionserver nach data/skins/<uuid>.png. Ohne eigenen Skin (Steve/Alex) gibt es keine Datei."""
    import base64, urllib.request
    try:
        with urllib.request.urlopen(f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid.replace('-', '')}", timeout=8) as r:
            prof = json.load(r)
        tex = next(json.loads(base64.b64decode(p["value"])) for p in prof.get("properties", []) if p.get("name") == "textures")
        url = tex.get("textures", {}).get("SKIN", {}).get("url")
        path = os.path.join(SKINS, uuid + ".png")
        if not url:
            if os.path.exists(path):
                os.remove(path)
            open(path + ".none", "w").close()  # merkt sich "kein Skin", damit nicht ständig neu gefragt wird
            return
        with urllib.request.urlopen(url.replace("http://", "https://"), timeout=8) as r:
            png = r.read(200_000)
        if png[:8] != b"\x89PNG\r\n\x1a\n":
            return
        tmp = path + ".tmp"
        open(tmp, "wb").write(png)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        if os.path.exists(path + ".none"):
            os.remove(path + ".none")
    except Exception:
        pass


def refresh_skins(uuids):
    """Holt fehlende oder alte Skins im Hintergrund, damit die 2-Sekunden-Schleife nicht wartet."""
    import threading
    os.makedirs(SKINS, exist_ok=True)
    now = time.time()
    due = []
    for u in uuids:
        f = os.path.join(SKINS, u + ".png")
        f = f if os.path.exists(f) else f + ".none"
        if not os.path.exists(f) or now - os.path.getmtime(f) > SKIN_EVERY:
            due.append(u)
    if due and not getattr(refresh_skins, "busy", False):
        def run():
            refresh_skins.busy = True
            try:
                for u in due:
                    fetch_skin(u)
                    time.sleep(1)  # Mojang begrenzt die Anfragen
            finally:
                refresh_skins.busy = False
        threading.Thread(target=run, daemon=True).start()


def skin_info(uuid):
    f = os.path.join(SKINS, uuid + ".png")
    try:
        with open(f, "rb") as fh:
            w, h = struct.unpack(">II", fh.read(24)[16:24])
        return {"src": f"data/skins/{uuid}.png?v={int(os.path.getmtime(f))}", "h": h if w == 64 else 64}
    except (OSError, struct.error):
        return None


# Dashboard-Statistik zurücksetzen, ohne Spielerdateien anzufassen: "collect.py --reset-stats" speichert den
# aktuellen Stand als Nullpunkt. Angezeigt wird nur, was seitdem dazugekommen ist. world/stats und
# world/advancements (Spielstand, Fortschritte im Spiel) bleiben unverändert.
BASELINE = os.path.join(STATE, "stats-baseline.json")


def read_stats(level, u):
    try:
        st = json.load(open(os.path.join(MC, level, "stats", u + ".json"), encoding="utf-8"))["stats"]
    except (OSError, ValueError, KeyError):
        st = None
    try:
        adv = json.load(open(os.path.join(MC, level, "advancements", u + ".json"), encoding="utf-8"))
        done = [k for k, v in adv.items() if isinstance(v, dict) and v.get("done") and "recipes/" not in k]
    except (OSError, ValueError):
        done = None
    return st, done


def reset_stats(level="world"):
    snap = {}
    for f in glob.glob(os.path.join(MC, level, "stats", "*.json")) + glob.glob(os.path.join(MC, level, "advancements", "*.json")):
        u = os.path.basename(f)[:-5]
        if u not in snap:
            st, done = read_stats(level, u)
            snap[u] = {"stats": st or {}, "adv": done or []}
    os.makedirs(STATE, exist_ok=True)
    json.dump({"time": int(time.time()), "players": snap}, open(BASELINE, "w", encoding="utf-8"))
    print(f"Nullpunkt gespeichert für {len(snap)} Spieler. Spielerdateien wurden nicht verändert.")


def load_baseline():
    try:
        return json.load(open(BASELINE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def minus(cur, base):
    """Zähler seit dem Nullpunkt; wird ein Zähler im Spiel kleiner (z. B. neue Welt), zählt er ab 0 neu."""
    out = {}
    for k, v in (cur or {}).items():
        d = v - (base or {}).get(k, 0)
        out[k] = d if d >= 0 else v
    return out


GUESTS = "/etc/void-draconic/gaeste.txt"  # ein Minecraft-Name pro Zeile; im Dashboard als "Gast" markiert


def guests():
    try:
        return {l.strip().lower() for l in open(GUESTS, encoding="utf-8") if l.strip() and not l.startswith("#")}
    except OSError:
        return set()


def players(online_names, level):
    names, wl = known_names()
    gs = guests()
    uuids = set(wl) | {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(MC, level, "stats", "*.json"))}
    refresh_skins(sorted(uuids))
    bl = load_baseline()
    online_lower = {n.lower() for n in online_names}
    out = []
    for u in sorted(uuids):
        name = names.get(u, u[:8])
        rec = {"uuid": u, "name": name, "online": name.lower() in online_lower, "whitelisted": u in wl, "play_time": 0,
               "skin": skin_info(u), "guest": name.lower() in gs}
        base = bl.get("players", {}).get(u, {})
        bst = base.get("stats", {})
        st, done = read_stats(level, u)
        if st is not None:
            cu = minus(st.get("minecraft:custom", {}), bst.get("minecraft:custom"))
            mined = minus(st.get("minecraft:mined", {}), bst.get("minecraft:mined"))
            killed = minus(st.get("minecraft:killed", {}), bst.get("minecraft:killed"))
            crafted = minus(st.get("minecraft:crafted", {}), bst.get("minecraft:crafted"))
            for k, key in CUSTOM.items():
                rec[k] = cu.get(key, 0)
            rec["play_time"] //= 20
            rec["dist"] = {k: round(sum(cu.get("minecraft:" + x, 0) for x in v) / 100) for k, v in DIST.items()}
            rec["mined"] = sum(mined.values())
            rec["crafted"] = sum(crafted.values())
            rec["top_kills"] = [[k.split(":")[-1], v] for k, v in sorted(killed.items(), key=lambda x: -x[1])[:3] if v]
            rec["top_mined"] = [[k.split(":")[-1], v] for k, v in sorted(mined.items(), key=lambda x: -x[1])[:3] if v]
            try:
                rec["last_seen"] = int(os.path.getmtime(os.path.join(MC, level, "stats", u + ".json")))
            except OSError:
                pass
        if done is not None:
            done = [k for k in done if k not in set(base.get("adv", []))]
            rec["advancements"] = sum(1 for k in done if k.startswith("minecraft:"))
            rec["advancements_mods"] = len(done) - rec["advancements"]
        else:
            rec["advancements"] = rec["advancements_mods"] = 0
        pd = os.path.join(MC, level, "playerdata", u + ".dat")
        if os.path.exists(pd):
            rec["last_seen"] = max(rec.get("last_seen", 0), int(os.path.getmtime(pd)))
        out.append(rec)
    out.sort(key=lambda r: (-r["online"], -r.get("play_time", 0)))
    return out


# ---------- Verlauf ----------
def history(point, now):
    with open(HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps(point, separators=(",", ":")) + "\n")
    rows = []
    for line in open(HIST, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r["t"] >= now - 7 * 86400:
            rows.append(r)
    if now % 3600 < 60:
        with open(HIST + ".tmp", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, separators=(",", ":")) + "\n" for r in rows)
        os.replace(HIST + ".tmp", HIST)
    day = [r for r in rows if r["t"] >= now - 86400]
    bucket = {}
    for r in rows:
        bucket.setdefault(r["t"] // 600 * 600, []).append(r)
    week = []
    for b in sorted(bucket):
        rs, avg = bucket[b], {"t": b}
        for k in ("tps", "mspt", "cpu", "ram"):
            vals = [r[k] for r in rs if r.get(k) is not None]
            avg[k] = round(sum(vals) / len(vals), 2) if vals else None
        avg["p"] = max((r.get("p") or 0) for r in rs)
        week.append(avg)
    return {"day": day, "week": week}


# ---------- Server-Beschreibung (MiniMOTD), Zeile 2 live ----------
MOTD = os.path.join(MC, "config", "MiniMOTD", "main.conf")
TAG = re.compile(r"<[^>]+>")


def motd_line(pregen, tps, ver):
    pg = pregen.get("minecraft:overworld", {})
    if pg.get("state") == "running":
        mid = f"<#C77DFF>Welt entsteht <white>{int(pg.get('percent', 0)) // 5 * 5} %"
    elif tps is not None:
        col = "#46C35B" if tps >= 19.5 else "#F5D547" if tps >= 15 else "#E5484D"
        mid = f"<#3FD0E0>TPS <{col}>{min(20, round(tps))}"
    else:
        mid = "<#3FD0E0>Refined Storage 2"
    line = f"<#46C35B>● <white><online_players><gray>/<max_players> online <dark_gray>• {mid} <dark_gray>• <#F5D547>v{ver}"
    visible = len(TAG.sub("", line)) + 3  # + Spielerzahl "0/6", die MiniMOTD einsetzt
    return " " * max(0, round((300 - 5.5 * visible) / 2 / 4)) + line  # Breite der Serverliste ca. 300 px


def update_motd(pregen, tps, ver, online):
    try:
        conf = open(MOTD, encoding="utf-8").read()
    except OSError:
        return
    new = motd_line(pregen, tps, ver).replace("\\", "\\\\").replace('"', '\\"')
    out, n = re.subn(r'^(\s*line2=")(?:[^"\\]|\\.)*(")', lambda m: m.group(1) + new + m.group(2), conf, count=1, flags=re.M)
    if not n or out == conf:
        return
    open(MOTD, "w", encoding="utf-8").write(out)
    if RCON.cmd("minimotd reload") is None and online:
        sh("sudo", "-u", "minecraft", "tmux", "send-keys", "-t", "mc", "minimotd reload", "Enter")


# ---------- Vorgenerierung nur, wenn niemand online ist ----------
JOB = os.path.join(STATE, "pregen-job.json")
RADIUS_DEFAULT = {"minecraft:overworld": 5000, "minecraft:the_nether": 2000, "minecraft:the_end": 2000}


QUEUE = os.path.join(STATE, "pregen-queue.json")        # weitere Aufträge, werden nacheinander gestartet
DONE = os.path.join(STATE, "pregen-history.json")       # erledigte Aufträge (für Messwerte)
CONTROL = os.path.join(STATE, "control")                 # schreibt die Dashboard-API (Schalter, Plan aus dem Rechner)


def read_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


class PregenGuard:
    """Auftrag in pregen-job.json: {"active": true, "world": "minecraft:overworld", "radius": 10000}.
    Immer nur eine Dimension zurzeit. Ist ein Auftrag fertig, startet der nächste aus pregen-queue.json.
    Schalter "Pausieren, wenn Spieler online" (control/pregen-settings.json, Standard an):
      an  -> sobald jemand online ist: chunky pause; ist IDLE Sekunden lang niemand online: chunky continue
      aus -> generiert auch, wenn Spieler online sind."""
    IDLE = 60

    def __init__(self):
        self.empty_since = None
        self.state = None  # "running" | "paused"

    def job(self):
        return read_json(JOB, {})

    def save(self, j):
        json.dump(j, open(JOB, "w", encoding="utf-8"))

    def watch(self):
        return read_json(os.path.join(CONTROL, "pregen-settings.json"), {}).get("watch_players", True)

    def next_job(self, now):
        q = read_json(QUEUE, [])
        if not q:
            return None
        j = {"active": True, "world": q[0]["world"], "radius": q[0]["radius"], "label": q[0].get("label"), "queued": now}
        json.dump(q[1:], open(QUEUE, "w", encoding="utf-8"))
        self.save(j)
        self.state = None
        return j

    def tick(self, now, live, pregen):
        j = self.job()
        if not live["online"]:
            self.state = None  # Server neu gestartet: Chunky läuft dann nicht mehr, später neu fortsetzen
            return j
        if not j.get("active"):
            return self.next_job(now) or j
        world = j.get("world", "minecraft:overworld")
        st = (pregen or {}).get(world, {})
        if j.get("started") and st.get("state") == "finished" and st.get("percent", 0) >= 100 and now - j["started"] > 120:
            j.update(active=False, finished=now, chunks=st.get("chunks"), total_time=st.get("total_time"))
            self.save(j)
            hist = read_json(DONE, [])
            json.dump((hist + [j])[-50:], open(DONE, "w", encoding="utf-8"))
            return self.next_job(now) or j
        players = live["players"]["online"] if self.watch() else 0
        if players:
            self.empty_since = None
            if self.state != "paused":
                RCON.cmd("chunky pause")
                self.state = "paused"
                j["paused_at"] = now
                self.save(j)
        else:
            self.empty_since = self.empty_since or now
            idle = self.IDLE if self.watch() else 0
            if self.state != "running" and now - self.empty_since >= idle:
                if not j.get("started"):
                    for c in (f"chunky world {world}", "chunky center 0 0", f"chunky radius {j.get('radius', 10000)}", "chunky start", "chunky confirm"):
                        RCON.cmd(c)
                    j["started"] = now
                else:
                    RCON.cmd("chunky continue")
                self.state = "running"
                j["resumed_at"] = now
                self.save(j)
        return j


GUARD = PregenGuard()


# ---------- Hauptschleife ----------
def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(STATE, exist_ok=True)
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    cpu = Cpu()
    live_ring, minute = [], []
    last_slow = last_min = 0
    slow = {}
    loop = "--once" not in sys.argv
    while True:
        t0 = time.time()
        now = int(t0)
        p = props()
        port = int(p.get("server-port", 25565))
        level = p.get("level-name", "world")

        # --- alle 2 s ---
        live = {"time": now, "address": ADDRESS, "online": False, "players": {"online": 0, "max": int(p.get("max-players", 0) or 0), "names": []}}
        try:
            sl = ping(port)
            pl = sl.get("players", {})
            live.update(online=True, version=sl.get("version", {}).get("name"), motd=plain(sl.get("description")),
                        players={"online": pl.get("online", 0), "max": pl.get("max", 0),
                                 "names": sorted(x.get("name", "") for x in pl.get("sample", []) or [])})
        except Exception as e:
            live["error"] = type(e).__name__
            RCON.close()
        tps = parse_tps(RCON.cmd("neoforge tps")) if live["online"] else None
        if tps:
            live["tps"] = tps
        if live["online"] and live["players"]["online"] and not live["players"]["names"]:
            lst = RCON.cmd("list")
            if lst and ":" in lst:
                live["players"]["names"] = sorted(n.strip() for n in lst.split(":", 1)[1].split(",") if n.strip())
        mem = meminfo()
        pid = java_pid()
        live["system"] = {"cpu": cpu.percent(), "cores": os.cpu_count(), "load": [round(x, 2) for x in os.getloadavg()],
                          "ram_total": mem["MemTotal"], "ram_used": mem["MemTotal"] - mem["MemAvailable"],
                          "java_rss": proc_rss(pid) if pid else None}
        pt = {"t": now, "cpu": live["system"]["cpu"], "ram": round(live["system"]["ram_used"] / 2**30, 2),
              "tps": (tps or {}).get("tps"), "mspt": (tps or {}).get("mspt"), "p": live["players"]["online"]}
        live_ring = [r for r in live_ring + [pt] if r["t"] > now - 600]
        minute.append(pt)
        live["ring"] = live_ring
        job = GUARD.tick(now, live, (slow.get("world") or {}).get("pregen"))
        watch = GUARD.watch()
        if job.get("active"):
            live["pregen_job"] = {"radius": job.get("radius"), "world": job.get("world"), "label": job.get("label"), "state": GUARD.state,
                                  "waiting": bool(GUARD.empty_since) and GUARD.state != "running" and not (live["players"]["online"] and watch)}
        live["pregen"] = {"watch": watch, "queue": read_json(QUEUE, []), "history": read_json(DONE, [])[-6:],
                          "plan": read_json(os.path.join(CONTROL, "pregen-plan.json"), None)}
        live["backup"] = backup_live(now)
        write_json("live.json", live)

        # --- alle 30 s ---
        if now - last_slow >= SLOW_EVERY or not loop:
            last_slow = now
            text = read_log_tail()
            names, _ = known_names()
            if now - cache.get("pack_t", 0) > 300:
                sha = sh("curl", "-fsS", "-m", "5", "-H", "Accept: application/vnd.github.sha", "https://api.github.com/repos/Bresqwik/void-draconic-pack/commits/main")
                ref = sha if re.fullmatch(r"[0-9a-f]{40}", sha or "") else "main"  # Commit-Pfad umgeht den raw-Cache
                m = re.search(r'version = "([^"]+)"', sh("curl", "-fsS", "-m", "5", f"https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/{ref}/pack.toml"))
                if m:
                    cache["pack_version"], cache["pack_t"] = m.group(1), now
            if now - cache.get("world_t", 0) > 600:
                dirs = ["overworld", "DIM-1", "DIM1"] + sorted(os.path.relpath(x, os.path.join(MC, level)).replace(os.sep, "/")
                                                            for x in glob.glob(os.path.join(MC, level, "dimensions", "*", "*")) if os.path.isdir(x))
                cache["world"] = {d: dir_size(os.path.join(MC, level, *([] if d == "overworld" else d.split("/")))) for d in dirs}
                cache["world_t"] = now
            du = os.statvfs("/")
            dims = {}
            if live["online"]:
                for d in ("minecraft:overworld", "minecraft:the_nether", "minecraft:the_end"):
                    e = entities(d)
                    if e:
                        dims[d] = e
            slow = {
                "time": now,
                "system": {"disk_total": du.f_blocks * du.f_frsize, "disk_used": (du.f_blocks - du.f_bfree) * du.f_frsize,
                           "uptime": int(float(open("/proc/uptime").read().split()[0])), "mc_since": service_since("void-draconic.service"),
                           "java_heap": "16 GB", "cpu_model": cache.get("cpu_model") or sh("sh", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip()},
                "pack": {"version": cache.get("pack_version"), "mods": len(glob.glob(os.path.join(MC, "mods", "*.jar"))),
                         "minecraft": live.get("version") or "1.21.1", "loader": "NeoForge 21.1.252"},
                "game": {"time": game_time() if live["online"] else None, "weather": weather(level), "entities": dims},
                "world": {"size": cache.get("world", {}), "size_time": cache.get("world_t"), "pregen": chunky_progress(text),
                          "radius": {**RADIUS_DEFAULT, **({GUARD.job().get("world", "minecraft:overworld"): GUARD.job()["radius"]} if GUARD.job().get("radius") else {})}},
                "backups": backups(),
                "events": events(text, set(names.values())),
            }
            cache["cpu_model"] = slow["system"]["cpu_model"]
            write_json("status.json", slow)
            update_motd(slow["world"]["pregen"], (tps or {}).get("tps"), slow["pack"]["version"] or "", live["online"])
            json.dump(cache, open(CACHE, "w", encoding="utf-8"))

        # --- jede Minute ---
        if now - last_min >= MIN_EVERY or not loop:
            last_min = now
            avg = {"t": now // 60 * 60, "p": max(r["p"] for r in minute)}
            for k in ("tps", "mspt", "cpu", "ram"):
                vals = [r[k] for r in minute if r.get(k) is not None]
                avg[k] = round(sum(vals) / len(vals), 2) if vals else None
            minute = []
            write_json("history.json", history(avg, now))
            write_json("players.json", {"time": now, "since": load_baseline().get("time"), "players": players(live["players"]["names"], level)})

        if not loop:
            break
        time.sleep(max(0.2, LIVE_EVERY - (time.time() - t0)))


if __name__ == "__main__":
    if "--reset-stats" in sys.argv:
        reset_stats(props().get("level-name", "world"))
    else:
        main()
