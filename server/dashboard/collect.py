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
import calendar, glob, gzip, json, os, re, socket, struct, subprocess, sys, threading, time, zipfile

MC = "/opt/void-draconic"
OUT = "/var/www/mc-dashboard/data"
STATE = "/var/lib/mc-dashboard"
HIST = os.path.join(STATE, "history.jsonl")
CACHE = os.path.join(STATE, "cache.json")
ADDRESS = "mc-void-draconic.bresqwik.org"
LIVE_EVERY, SLOW_EVERY, MIN_EVERY = 2, 30, 60
DIM_NAMES = {"Overworld": "minecraft:overworld", "The Nether": "minecraft:the_nether", "The End": "minecraft:the_end"}
DIM_LABEL = {v: k for k, v in DIM_NAMES.items()}


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
    """Forge 1.20.1: 'Dim minecraft:overworld (minecraft:overworld): Mean tick time: 2,030 ms. Mean TPS: 20,000' … 'Overall: …'.
    Älteres NeoForge-Format 'Overworld: 20,000 TPS (0,443 ms/tick)' geht weiterhin (deutsches Dezimalkomma möglich)."""
    if not text:
        return None
    res = {"dims": {}}
    for m in re.finditer(r"(?:Dim\s+(\S+)\s+\([^)]*\)|(Overall)):\s*Mean tick time:\s*([\d.,]+)\s*ms\.\s*Mean TPS:\s*([\d.,]+)", text):
        name, ms, tps = m.group(1) or m.group(2), num(m.group(3)), num(m.group(4))
        if name == "Overall":
            res["tps"], res["mspt"] = tps, ms
        else:
            res["dims"][name] = {"name": DIM_LABEL.get(name, name), "tps": tps, "mspt": ms}
    for m in re.finditer(r"([^\n:]+(?::[a-z0-9_/.-]+)?):\s*([\d.,]+)\s*TPS\s*\(([\d.,]+)\s*ms/tick\)", text):
        name, tps, ms = m.group(1).strip(), num(m.group(2)), num(m.group(3))
        if name == "Overall":
            res["tps"], res["mspt"] = tps, ms
        else:
            res["dims"][DIM_NAMES.get(name, name)] = {"name": name, "tps": tps, "mspt": ms}
    return res if "tps" in res else None


def entities(dim):
    out = RCON.cmd(f"execute in {dim} run forge entity list")
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


def chunky_tasks():
    """Gespeicherte Chunky-Aufträge (config/chunky/tasks/<ns>/<welt>.properties). Überstehen Neustarts,
    anders als die Log-Zeilen. Fortschritt = Chunks / Chunks im Quadrat des Radius."""
    res = {}
    for f in glob.glob(os.path.join(MC, "config", "chunky", "tasks", "*", "*.properties")):
        try:
            kv = dict(l.strip().split("=", 1) for l in open(f, encoding="utf-8") if "=" in l)
            r = float(kv.get("radius", 0))
            side = 2 * -(-int(r) // 16) + 1
            n = int(kv.get("chunks", 0))
            pct = min(100.0, round(n / side ** 2 * 100, 1)) if r else 0.0
            done = kv.get("cancelled") == "true" and pct >= 99.5
            t = int(kv.get("time", 0)) // 1000
            res[kv["world"]] = {"state": "finished" if done else "paused", "chunks": n, "percent": 100.0 if done else pct,
                                "radius": int(r), **({"total_time": f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"} if done else {})}
        except (OSError, ValueError, KeyError):
            pass
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
        for k in ("tps", "mspt", "cpu", "ram", "cps"):
            vals = [r[k] for r in rs if r.get(k) is not None]
            avg[k] = round(sum(vals) / len(vals), 2) if vals else None
        avg["p"] = max((r.get("p") or 0) for r in rs)
        week.append(avg)
    return {"day": day, "week": week}


# ---------- Server-Beschreibung (MiniMOTD), Zeile 2 live ----------
MOTD = os.path.join(MC, "config", "minimotd", "main.conf")
TAG = re.compile(r"<[^>]+>")


def motd_line(pregen, tps, ver):
    pg = pregen.get("minecraft:overworld", {})
    if pg.get("state") == "running":
        mid = f"<#C77DFF>Welt entsteht <white>{int(pg.get('percent', 0)) // 5 * 5} %"
    elif tps is not None:
        col = "#46C35B" if tps >= 19.5 else "#F5D547" if tps >= 15 else "#E5484D"
        mid = f"<#3FD0E0>TPS <{col}>{min(20, round(tps))}"
    else:
        mid = "<#3FD0E0>Botania · Mekanism · Create"
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


WORLD_BYTES = 0          # Größe des Weltordners (alle Dimensionen), alle 10 Min. aus dem langsamen Durchlauf
DISK_MARGIN = 15 * 2**30  # Puffer zusätzlich zum Platz für ein Voll-Backup (ZIP ≈ Weltgröße)


def disk_brake():
    """Speicherbremse: Für ein Voll-Backup muss etwa die Weltgröße frei sein, dazu 15 GB Puffer.
    Gibt (frei, nötig) in Bytes zurück, wenn der Platz NICHT reicht, sonst None."""
    st = os.statvfs("/")
    free, need = st.f_bavail * st.f_frsize, WORLD_BYTES + DISK_MARGIN
    return (free, need) if WORLD_BYTES and free < need else None


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

    def control(self, now):
        """Start/Stopp-Schalter im Dashboard (control/pregen-run.json, nur Admin). Stopp sichert Auftrag und
        Warteschlange in *.gestoppt.json, Start setzt sie fort (Chunky überspringt fertige Chunks)."""
        p = os.path.join(CONTROL, "pregen-run.json")
        c = read_json(p, None)
        if c is None:
            return
        try:
            os.remove(p)
        except OSError:
            pass
        j, who = self.job(), str(c.get("by") or "Dashboard")
        stop_job, stop_q = os.path.join(STATE, "pregen-job.gestoppt.json"), os.path.join(STATE, "pregen-queue.gestoppt.json")
        result = "nichts zu tun"
        if c.get("run") is False and j.get("active"):
            RCON.cmd("chunky pause")
            j.update(active=False, paused_for=f"Gestoppt im Dashboard ({who})", stopped_at=now)
            json.dump(j, open(stop_job, "w", encoding="utf-8"))
            self.save(j)
            q = read_json(QUEUE, [])
            if q:
                json.dump(q, open(stop_q, "w", encoding="utf-8"))
                json.dump([], open(QUEUE, "w", encoding="utf-8"))
            self.state = None
            result = "Vorgenerierung gestoppt, Plan gesichert"
        elif c.get("run") is True and not j.get("active"):
            s = read_json(stop_job, None)
            if s and not s.get("finished"):
                s = {k: v for k, v in s.items() if k not in ("paused_for", "stopped_at")}
                s.update(active=True, resumed_by=who)
                self.save(s)
                os.replace(stop_job, stop_job.replace(".gestoppt.", ".fortgesetzt."))
                result = f"Vorgenerierung fortgesetzt: {s.get('label') or s.get('world')}"
            q = read_json(stop_q, None)
            if q and not read_json(QUEUE, []):
                json.dump(q, open(QUEUE, "w", encoding="utf-8"))
                os.replace(stop_q, stop_q.replace(".gestoppt.", ".fortgesetzt."))
                if result == "nichts zu tun":
                    result = "Warteschlange fortgesetzt"
            self.state = None
        log = read_json(ADMIN_LOG, [])
        log.append({"player": "Weltgenerierung", "action": "pregen-start" if c.get("run") else "pregen-stop", "by": who,
                    "time": c.get("time", now), "ok": result != "nichts zu tun", "result": result, "done": now})
        tmp = ADMIN_LOG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(log[-30:], fh, ensure_ascii=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, ADMIN_LOG)

    @staticmethod
    def saved_task(world, radius):
        """Gibt es in config/chunky/tasks einen nicht abgebrochenen Auftrag für diese Welt mit gleichem Radius und Mitte 0/0?"""
        ns, _, name = world.partition(":")
        p = os.path.join(MC, "config", "chunky", "tasks", ns, name + ".properties")
        try:
            kv = dict(l.split("=", 1) for l in open(p).read().splitlines() if "=" in l)
            return (kv.get("cancelled") != "true" and float(kv.get("radius", 0)) == float(radius)
                    and float(kv.get("center-x", 1)) == 0 and float(kv.get("center-z", 1)) == 0)
        except (OSError, ValueError):
            return False

    def tick(self, now, live, pregen):
        self.control(now)
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
        if self.state == "running" and j.get("started") and now - j.get("resumed_at", now) > 180 and st.get("state") not in ("running", "finished"):
            if "no tasks" in (RCON.cmd("chunky progress") or "").lower():
                self.state = None
        brake = disk_brake()
        if brake:
            if self.state != "paused" or not j.get("brake"):
                RCON.cmd("chunky pause")
                self.state = "paused"
                j.update(brake=f"Speicherbremse: {brake[0] / 2**30:.0f} GB frei, für Backup + Puffer nötig {brake[1] / 2**30:.0f} GB", paused_at=now)
                self.save(j)
                print(j["brake"], flush=True)
            return j
        if j.pop("brake", None):
            self.save(j)
            self.state = None  # Platz wieder da: normal fortsetzen
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
                    if self.saved_task(world, j.get("radius", 10000)):
                        # gespeicherter Chunky-Auftrag mit gleichem Radius: fortsetzen statt von vorn durchzählen
                        cmds = (f"chunky world {world}", f"chunky continue {world}")
                    else:
                        cmds = (f"chunky world {world}", "chunky center 0 0", f"chunky radius {j.get('radius', 10000)}", "chunky start", "chunky confirm")
                    out = [RCON.cmd(c) for c in cmds]
                    if any(o is None for o in out):
                        return j  # RCON noch nicht bereit (Server startet): im nächsten Durchlauf erneut versuchen
                    j["started"] = now
                else:
                    out = RCON.cmd(f"chunky continue {world}") or ""
                    if "no task" in out.lower() or "keine" in out.lower():
                        # Nach einem Server-Neustart ist der Chunky-Auftrag weg: neu starten (fertige Chunks überspringt Chunky schnell)
                        for c in (f"chunky world {world}", "chunky center 0 0", f"chunky radius {j.get('radius', 10000)}", "chunky start", "chunky confirm"):
                            RCON.cmd(c)
                self.state = "running"
                j["resumed_at"] = now
                self.save(j)
        return j


GUARD = PregenGuard()


# ---------- Backup, sobald alle Spieler weg sind (online macht Simple Backups nur alle 8 Std. eins) ----------
def last_backup_time():
    """Zeit des neuesten Backups aus den Dateinamen (world_JJJJ-MM-TT_hh-mm-ss.zip): lokal wartende und schon hochgeladene."""
    names = [os.path.basename(f) for f in glob.glob(os.path.join(MC, "simplebackups", "**", "*.zip"), recursive=True)]
    sync = read_json(SYNC_STATE, {})
    names += [f.get("name", "") for f in (sync.get("cloud") or {}).get("files", [])] + [(sync.get("last_upload") or {}).get("name", "")]
    best = 0
    for n in names:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.zip$", n or "")
        if m:
            best = max(best, time.mktime(tuple(int(x) for x in m.groups()) + (0, 0, -1)))
    return int(best)


class LeaveBackup:
    IDLE = 300       # so lange muss der Server leer sein
    MIN_AGE = 3600   # nur, wenn das letzte Backup älter ist

    def __init__(self):
        self.had_players = False
        self.empty_since = None

    def tick(self, now, live):
        if not live["online"]:
            self.empty_since = None
            return
        if live["players"]["online"]:
            self.had_players, self.empty_since = True, None
            return
        if not self.had_players:
            return
        self.empty_since = self.empty_since or now
        if now - self.empty_since < self.IDLE:
            return
        self.had_players = False  # einmal pro Leerlauf
        age = now - (last_backup_time() or 0)
        if age >= self.MIN_AGE:
            out = RCON.cmd("simplebackups backup start")
            print(f"Backup nach Verlassen gestartet (letztes vor {age // 60} Min.): {(out or '').strip()[:120]}", flush=True)


LEAVE_BACKUP = LeaveBackup()


# ---------- Details zu Online-Spielern (für die Online-Liste), alle 10 s per RCON ----------
def entity_data(name, path):
    out = RCON.cmd(f"data get entity {name} {path}") or ""
    m = re.search(r"has the following entity data: (.*)$", out.strip(), re.S)
    return m.group(1).strip() if m else None


def player_details(names):
    res = {}
    for n in names:
        if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", n):
            continue
        d = {}
        dim = entity_data(n, "Dimension")
        if dim:
            d["dim"] = dim.strip('"')
        pos = entity_data(n, "Pos")
        nums = re.findall(r"-?\d+(?:\.\d+)?", pos or "")
        if len(nums) >= 3:
            d["pos"] = [int(float(x)) for x in nums[:3]]
        for key, path, cast in (("health", "Health", float), ("food", "foodLevel", int), ("level", "XpLevel", int)):
            v = entity_data(n, path)
            m = re.match(r"-?\d+(?:\.\d+)?", v or "")
            if m:
                d[key] = cast(float(m.group(0)))
        res[n] = d
    return res


# ---------- Spieler-Aktionen aus dem Dashboard (nur Admin-Konto, geprüft in auth.py) ----------
ADMIN_LOG = os.path.join(CONTROL, "admin-log.json")
# Dashboard-Konto -> eigener Minecraft-Name (für "Zu mir holen" / "Ich zu ihm")
ADMIN_INGAME = {"mero": "stman476"}


def world_spawn(level):
    """Weltspawn aus level.dat (SpawnX/Y/Z), ohne NBT-Bibliothek."""
    try:
        d = gzip.open(os.path.join(MC, level, "level.dat")).read()
        out = []
        for k in (b"SpawnX", b"SpawnY", b"SpawnZ"):
            i = d.find(b"\x03" + struct.pack(">H", len(k)) + k)
            out.append(struct.unpack(">i", d[i + 3 + len(k):i + 7 + len(k)])[0])
        return out
    except (OSError, struct.error, ValueError):
        return [0, 100, 0]


# ---------- Mystical-Agriculture-Fortschritt von byLapus2 (vorübergehend, bis „MA abgekapselt“ live ist) ----------
# Liest das Questkapitel und die Team-Datei direkt (kein Neustart nötig). Reihenfolge = Questbuch (Abhängigkeiten),
# dazu Erledigt-Zeitpunkt, Teilfortschritt der Aufgaben und eine kurze Beschreibung der offenen Quests.
MA_CHAPTER = os.path.join(MC, "config/ftbquests/quests/chapters/mystical_agriculture.snbt")
MA_TEAM = os.path.join(MC, "world/ftbquests/83fa4a35-d482-4e79-ba6b-5345847bf837.snbt")
MA_PLAYER = "byLapus2"
_ma = {"key": None, "data": None, "lang": None}
SNBT_TOKEN = re.compile(r'\s*(?:(")((?:[^"\\]|\\.)*)"|([{}\[\]:,;])|([^\s{}\[\]:,;"]+))')


def snbt(text):
    """Minimaler SNBT-Leser für FTB-Quests-Dateien (Zeilenumbruch trennt Einträge wie ein Komma)."""
    toks, pos = [], 0
    while True:
        m = SNBT_TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group(1):
            toks.append(("s", re.sub(r'\\(.)', r'\1', m.group(2))))
        elif m.group(3):
            toks.append(("p", m.group(3)))
        else:
            toks.append(("w", m.group(4)))
    i = 0

    def val():
        nonlocal i
        t, v = toks[i]
        i += 1
        if t == "p" and v == "{":
            obj = {}
            while toks[i] != ("p", "}"):
                if toks[i] == ("p", ","):
                    i += 1
                    continue
                k = toks[i][1]
                i += 2  # Schlüssel und ":"
                obj[k] = val()
            i += 1
            return obj
        if t == "p" and v == "[":
            arr = []
            if i + 1 < len(toks) and toks[i + 1] == ("p", ";"):
                i += 2  # [I; …]
            while toks[i] != ("p", "]"):
                if toks[i] == ("p", ","):
                    i += 1
                    continue
                arr.append(val())
            i += 1
            return arr
        if t == "s":
            return v
        m2 = re.fullmatch(r"(-?\d+(?:\.\d+)?)[bBsSlLfFdD]?", v)
        if m2:
            return float(m2.group(1)) if "." in m2.group(1) else int(m2.group(1))
        return {"true": True, "false": False}.get(v, v)

    return val()


def ma_lang():
    if _ma["lang"] is None:
        lang = {}
        for jar in glob.glob(os.path.join(MC, "mods", "Mystical*.jar")):
            try:
                with zipfile.ZipFile(jar) as z:
                    for n in z.namelist():
                        if n.endswith("/lang/de_de.json"):
                            lang.update(json.loads(z.read(n).decode("utf-8")))
            except (OSError, zipfile.BadZipFile, ValueError):
                pass
        _ma["lang"] = lang
    return _ma["lang"]


def ma_item_name(item_id):
    ns, _, path = item_id.partition(":")
    lang = ma_lang()
    for k in (f"item.{ns}.{path}", f"block.{ns}.{path}"):
        if k in lang:
            return lang[k]
    # Samen/Essenzen/Krux der Pflanzen: „%s Samen“ mit dem Pflanzennamen (crop.<mod>.<name>)
    m = re.fullmatch(r"(.+)_(seeds|essence|crux)", path)
    if m:
        crop = next((lang[k] for k in (f"crop.mysticalagriculture.{m.group(1)}", f"crop.mysticalagradditions.{m.group(1)}") if k in lang),
                    {"nether_star": "Netherstern", "dragon_egg": "Drachenei", "awakened_draconium": "Erwecktes Draconium"}.get(m.group(1)))
        if crop:
            fmt = {"seeds": lang.get("item.mysticalagriculture.mystical_seeds", "%s Samen"),
                   "essence": lang.get("item.mysticalagriculture.mystical_essence", "%s Essenz"), "crux": "%s-Krux"}[m.group(2)]
            return fmt.replace("%s", crop)
    return path.replace("_", " ").title()


def ma_plain(s):
    return re.sub(r"[&§][0-9a-fk-or]", "", s or "").strip()


def ma_short(desc):
    """Erster sachlicher Absatz (ohne kursive Lore-Zeile), auf ~170 Zeichen gekürzt."""
    lines = [ma_plain(l) for l in (desc or []) if l and not l.lstrip().startswith("&5&o") and not l.startswith("{")]
    text = " ".join(l for l in lines if l)
    if len(text) > 170:
        cut = text[:170]
        dot = cut.rfind(". ")
        text = cut[:dot + 1] if dot > 80 else cut.rsplit(" ", 1)[0] + " …"
    return text


def ma_progress():
    try:
        key = (os.path.getmtime(MA_CHAPTER), os.path.getmtime(MA_TEAM))
    except OSError:
        return None
    if key == _ma["key"]:
        return _ma["data"]
    try:
        chap = snbt(open(MA_CHAPTER, encoding="utf-8").read())
        team = snbt(open(MA_TEAM, encoding="utf-8").read())
    except (OSError, IndexError, KeyError, ValueError) as e:
        print("MA-Fortschritt:", e, file=sys.stderr)
        return _ma["data"]
    done = {str(k): v for k, v in (team.get("completed") or {}).items()}
    prog = {str(k): v for k, v in (team.get("task_progress") or {}).items()}
    quests = chap.get("quests") or []
    by_id = {q["id"]: q for q in quests}
    # Reihenfolge: Abhängigkeiten zuerst, sonst Position im Questbuch (y, dann x)
    order, seen = [], set()

    def visit(q):
        if q["id"] in seen:
            return
        seen.add(q["id"])
        for d in q.get("dependencies") or []:
            if d in by_id:
                visit(by_id[d])
        order.append(q)

    for q in sorted(quests, key=lambda q: (q.get("y", 0), q.get("x", 0))):
        visit(q)
    times = sorted(done[q["id"]] for q in quests if q["id"] in done)
    out = []
    for n, q in enumerate(order, 1):
        tasks = []
        for t in q.get("tasks") or []:
            item = (t.get("item") or {}).get("id") if isinstance(t.get("item"), dict) else t.get("item")
            need = int(t.get("count") or 1)
            have = need if q["id"] in done else min(int(prog.get(str(t.get("id")), 0) or 0), need)
            tasks.append({"name": ma_item_name(item) if item else ma_plain(t.get("title")) or t.get("type"), "have": have, "need": need})
        t_done = done.get(q["id"])
        out.append({"n": n, "id": q["id"], "title": ma_plain(q.get("title")), "done": t_done,
                    "rank": times.index(t_done) + 1 if t_done else None, "optional": bool(q.get("optional")),
                    "deps": [ma_plain(by_id[d].get("title")) for d in q.get("dependencies") or [] if d in by_id],
                    "short": None if t_done else ma_short(q.get("description")), "tasks": tasks})
    data = {"player": MA_PLAYER, "chapter": ma_plain(chap.get("title")), "total": len(out),
            "done": sum(1 for q in out if q["done"]), "quests": out, "time": int(time.time())}
    _ma.update(key=key, data=data)
    return data


# ---------- /lag-Meldungen der Spieler (KubeJS legt lag-reports/*.json ab) ----------
LAG_LOG = os.path.join(STATE, "lag-log.json")
LAG_ARCHIVE = os.path.join(STATE, "lag-archiv.json")
MELD_LOG = os.path.join(STATE, "meldungen.json")          # /meldung der Spieler (KubeJS legt meldungen/*.json ab)
MELD_ARCHIVE = os.path.join(STATE, "meldungen-archiv.json")


# ---------- Claims & Last (KubeJS claims_load.js schreibt alle 5 Min. vd-claims.json) ----------
CLAIMS_FILE = os.path.join(MC, "vd-claims.json")
_claims = {"mtime": 0, "data": None}


def claims_data():
    try:
        mt = os.path.getmtime(CLAIMS_FILE)
    except OSError:
        return None
    if mt != _claims["mtime"]:
        d = read_json(CLAIMS_FILE, None)
        if d:
            names, _ = known_names()
            for t in d.get("teams", []):
                t["members"] = [names.get(m, m) for m in t.get("members", [])]
        _claims.update(mtime=mt, data=d)
    return _claims["data"]


# ---------- Sprungkönig (KubeJS sprungkoenig.js schreibt vd-sprung.json, solange prexynation online ist) ----------
SPRUNG_FILE = os.path.join(MC, "vd-sprung.json")
SPRUNG_PLAYER = "prexynation"


def sprung_data(level="world"):
    """Live-Stand aus KubeJS; fehlt die Datei (noch), Stand aus world/stats (wird beim Speichern aktualisiert)."""
    d = read_json(SPRUNG_FILE, None)
    if d and d.get("jumps") is not None:
        return d
    names, _ = known_names()
    uuid = next((u for u, n in names.items() if n.lower() == SPRUNG_PLAYER), None)
    if not uuid:
        return None
    try:
        f = os.path.join(MC, level, "stats", uuid + ".json")
        st = json.load(open(f, encoding="utf-8"))["stats"].get("minecraft:custom", {})
    except (OSError, ValueError, KeyError):
        return None
    jumps, hours = st.get("minecraft:jump", 0), st.get("minecraft:play_time", 0) / 72000
    return {"player": SPRUNG_PLAYER, "jumps": jumps, "play_hours": round(hours, 1),
            "per_hour": round(jumps / hours) if hours else None, "milestone": 50000, "goal": 100000,
            "done_50k": jumps >= 50000, "done_100k": jumps >= 100000, "time": int(os.path.getmtime(f) * 1000), "source": "stats"}


def lag_reports(live):
    """Neue Meldungen einsammeln, mit Pregen-Stand und Systemlast ergänzen, nach lag-reports/erledigt verschieben."""
    files = sorted(glob.glob(os.path.join(MC, "lag-reports", "*.json")))
    if not files:
        return
    log = read_json(LAG_LOG, [])
    done = os.path.join(MC, "lag-reports", "erledigt")
    os.makedirs(done, exist_ok=True)
    pn = live.get("pregen_now") or {}
    for f in files:
        r = read_json(f, None)
        try:
            os.replace(f, os.path.join(done, os.path.basename(f)))
        except OSError:
            pass
        if not isinstance(r, dict) or "player" not in r:
            continue
        r["pregen"] = {"world": pn.get("world"), "rate": pn.get("rate"), "percent": pn.get("percent")} if pn else None
        r["system"] = {k: (live.get("system") or {}).get(k) for k in ("cpu", "load", "ram_used")}
        r["log_hint"] = "latest.log: Suchwort LAG-MARKE " + time.strftime("%H:%M:%S", time.localtime(r.get("time", 0) / 1000))
        log.append(r)
        print(f"Lag gemeldet von {r['player']} in {r.get('dim')} (MSPT {r.get('mspt')})", flush=True)
    save_lag(LAG_LOG, log[-50:])


def save_lag(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def lag_key(r):
    return f"{r.get('time')}-{r.get('player')}"


def meld_reports():
    """/meldung der Spieler einsammeln und nach meldungen/erledigt verschieben."""
    files = sorted(glob.glob(os.path.join(MC, "meldungen", "*.json")))
    if not files:
        return
    log = read_json(MELD_LOG, [])
    done = os.path.join(MC, "meldungen", "erledigt")
    os.makedirs(done, exist_ok=True)
    for f in files:
        r = read_json(f, None)
        try:
            os.replace(f, os.path.join(done, os.path.basename(f)))
        except OSError:
            pass
        if not isinstance(r, dict) or "player" not in r:
            continue
        r["log_hint"] = "Log: [Meldung] " + time.strftime("%H:%M:%S", time.localtime(r.get("time", 0) / 1000))
        log.append(r)
        print(f"Meldung von {r['player']}: {str(r.get('text'))[:120]}", flush=True)
    save_lag(MELD_LOG, log[-100:])


def lag_actions(prefix="lag", log_path=LAG_LOG, arch_path=LAG_ARCHIVE):
    """Knöpfe im Dashboard (nur Admin): Meldung archivieren, aus dem Archiv zurückholen oder endgültig löschen.
    prefix "lag" = Lag-Meldungen, "meld" = /meldung."""
    files = sorted(glob.glob(os.path.join(CONTROL, prefix + "-*.json")))
    if not files:
        return
    log, arch = read_json(log_path, []), read_json(arch_path, [])
    for f in files:
        a = read_json(f, None) or {}
        try:
            os.remove(f)
        except OSError:
            pass
        k, act = a.get("key"), a.get("action")
        if act == "archive":
            hit = [r for r in log if lag_key(r) == k]
            log = [r for r in log if lag_key(r) != k]
            arch += [{**r, "archived": int(time.time()), "archived_by": a.get("by")} for r in hit]
        elif act == "restore":
            hit = [r for r in arch if lag_key(r) == k]
            arch = [r for r in arch if lag_key(r) != k]
            log = sorted(log + [{x: v for x, v in r.items() if x not in ("archived", "archived_by")} for r in hit], key=lambda r: r.get("time", 0))
        elif act == "delete":
            log = [r for r in log if lag_key(r) != k]
            arch = [r for r in arch if lag_key(r) != k]
        print(f"{prefix}-Meldung {k}: {act} durch {a.get('by')}", flush=True)
    save_lag(log_path, log[-100:])
    save_lag(arch_path, arch[-200:])


def player_actions(level):
    files = sorted(glob.glob(os.path.join(CONTROL, "action-*.json")))
    if not files:
        return
    log = read_json(ADMIN_LOG, [])
    for f in files:
        a = read_json(f, None)
        try:
            os.remove(f)
        except OSError:
            pass
        if not a or not re.fullmatch(r"[A-Za-z0-9_]{3,16}", str(a.get("player", ""))):
            continue
        n, act, text = a["player"], a.get("action"), re.sub(r"[\x00-\x1f]", " ", str(a.get("text") or ""))[:200]
        if act == "kick":
            cmds = [f"kick {n} {text or 'Vom Admin getrennt'}"]
        elif act in ("op", "deop"):
            cmds = [f"{act} {n}"]
        elif act == "spawn":
            x, y, z = world_spawn(level)
            cmds = [f"execute in minecraft:overworld run tp {n} {x} {y + 1} {z}",
                    f"execute in minecraft:overworld run spreadplayers {x} {z} 0 3 false {n}"]
        elif act == "clear":
            cmds = [f"effect clear {n}"]
        elif act == "death":
            d = entity_data(n, "LastDeathLocation") or ""
            m = re.search(r"pos: \[I; (-?\d+), (-?\d+), (-?\d+)\], dimension: \"([a-z0-9_:/.-]+)\"", d)
            if not m:
                log.append({**a, "ok": False, "result": "kein Todespunkt bekannt", "done": int(time.time())})
                continue
            x, y, z, dim = m.groups()
            cmds = [f"execute in {dim} run tp {n} {x} {int(y) + 1} {z}"]
        elif act in ("bring", "goto"):
            me = ADMIN_INGAME.get(str(a.get("by", "")).lower())
            if not me:
                log.append({**a, "ok": False, "result": "kein Minecraft-Name für dieses Konto hinterlegt", "done": int(time.time())})
                continue
            cmds = [f"tp {n} {me}" if act == "bring" else f"tp {me} {n}"]
        elif act == "heal":
            cmds = [f"effect give {n} minecraft:instant_health 1 4 true", f"effect give {n} minecraft:saturation 1 10 true"]
        elif act == "msg" and text:
            cmds = ["tellraw %s %s" % (n, json.dumps([{"text": "[Admin] ", "color": "gold"}, {"text": text, "color": "white"}], ensure_ascii=False))]
        else:
            continue
        out = [RCON.cmd(c) for c in cmds]
        # Minecraft meldet Fehler als normale Antwort: als fehlgeschlagen werten
        ok = all(o is not None for o in out) and not any(re.search(r"No (player|entity) was found|Unknown|Incorrect|Expected|nicht gefunden", o or "") for o in out)
        log.append({**a, "ok": ok, "result": " | ".join((o or "").strip() for o in out if o and o.strip())[:300] or ("ausgeführt" if ok else "Server nicht erreichbar"),
                    "done": int(time.time())})
    save_admin_log(log)


def save_admin_log(log):
    tmp = ADMIN_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(log[-30:], fh, ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ADMIN_LOG)


# ---------- Chat (Minecraft-Chat im Dashboard, lesen + schreiben) ----------
# Liest latest.log stückweise ab der zuletzt gelesenen Stelle (nach Neustart/Rotation von vorn) und hält die
# letzten CHAT_KEEP Einträge in chat.json, damit der Verlauf Neustarts übersteht. Nachrichten aus dem Dashboard
# legt auth.py als control/chat-*.json ab; sie gehen per tellraw an alle (tellraw steht nicht im Log).
CHAT_FILE = os.path.join(STATE, "chat.json")
CHAT_KEEP, CHAT_SHOW = 300, 120
MONTHS = {"jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4, "mai": 5, "may": 5, "jun": 6, "jul": 7, "aug": 8,
          "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12}
CHAT_RX = re.compile(r"^\[(\d\d)([^\W\d_]+)\.?(\d{4}) (\d\d):(\d\d):(\d\d)\.\d+\] \[Server thread/INFO\] "
                     r"\[net\.minecraft\.server\.MinecraftServer/\]: (?:\[Not Secure\] )?(.+)$")


def chat_entry(rest, names):
    m = re.match(r"<([A-Za-z0-9_]{1,16})> (.*)$", rest)
    if m:
        return {"kind": "chat", "name": m.group(1), "msg": m.group(2)[:300]}
    m = re.match(r"\[(Server|Rcon)\] (.*)$", rest)
    if m:
        return {"kind": "say", "name": "Server", "msg": m.group(2)[:300]}
    m = re.match(r"([A-Za-z0-9_]{3,16}) (.*)$", rest)
    if not m or m.group(1) not in names():
        return None
    name, rest = m.groups()
    if rest == "joined the game":
        return {"kind": "join", "name": name, "msg": "ist beigetreten"}
    if rest == "left the game":
        return {"kind": "leave", "name": name, "msg": "hat das Spiel verlassen"}
    if rest.startswith(("has made the advancement", "has completed the challenge", "has reached the goal")):
        return {"kind": "adv", "name": name,
                "msg": "Fortschritt: " + re.sub(r"^has (made the advancement|completed the challenge|reached the goal)\s*", "", rest).strip("[] ")}
    if DEATH.search(rest) and not rest.startswith(("issued server command", "lost connection")):
        return {"kind": "death", "name": name, "msg": rest[:200]}
    return None


class Chat:
    def __init__(self):
        self.items = read_json(CHAT_FILE, [])
        self.keys = {e.get("k") for e in self.items}
        self.pos, self.ino = 0, None
        self._names = None
        if not os.path.exists(CHAT_FILE):      # erster Start: Verlauf aus den letzten gepackten Logs übernehmen
            for f in sorted(glob.glob(os.path.join(MC, "logs", "20*.log.gz")), key=os.path.getmtime)[-3:]:
                try:
                    self.parse(gzip.open(f).read().decode("utf-8", "replace"))
                except (OSError, EOFError):
                    pass
            self.save()

    def add(self, e):
        if e["k"] in self.keys:
            return False
        self.items.append(e)
        self.keys.add(e["k"])
        return True

    def names(self):
        if self._names is None:
            self._names = set(known_names()[0].values())
        return self._names

    def read_log(self):
        path = os.path.join(MC, "logs", "latest.log")
        try:
            st = os.stat(path)
        except OSError:
            return False
        if st.st_ino != self.ino or st.st_size < self.pos:
            self.ino, self.pos = st.st_ino, 0
        if st.st_size == self.pos:
            return False
        with open(path, "rb") as f:
            f.seek(self.pos)
            data = f.read(4_000_000)
        cut = data.rfind(b"\n") + 1          # nur ganze Zeilen, der Rest kommt im nächsten Durchlauf
        self.pos += cut
        return self.parse(data[:cut].decode("utf-8", "replace"))

    def parse(self, text):
        self._names, changed = None, False
        for line in text.splitlines():
            m = CHAT_RX.match(line)
            if not m:
                continue
            d, mon, y, hh, mi, ss, rest = m.groups()
            e = chat_entry(rest, self.names)
            if not e:
                continue
            try:
                t = int(time.mktime((int(y), MONTHS.get(mon[:3].lower(), 1), int(d), int(hh), int(mi), int(ss), 0, 0, -1)))
            except (OverflowError, ValueError):
                t = int(time.time())
            changed |= self.add({"k": line[1:24] + "|" + rest[:60], "t": t, **e})
        return changed

    def post(self, online):
        changed = False
        for f in sorted(glob.glob(os.path.join(CONTROL, "chat-*.json"))):
            a = read_json(f, None) or {}
            try:
                os.remove(f)
            except OSError:
                pass
            text = re.sub(r"[\x00-\x1f]", " ", str(a.get("text") or "")).strip()[:200]
            by = str(a.get("by") or "")
            by = ADMIN_INGAME.get(by.lower()) or re.sub(r"[^A-Za-z0-9_ .-]", "", by)[:16] or "Web"
            if not text:
                continue
            raw = json.dumps(["", {"text": "[Web] ", "color": "aqua"}, {"text": f"<{by}> ", "color": "white"},
                              {"text": text, "color": "white"}], ensure_ascii=False)
            ok = bool(online) and RCON.cmd("tellraw @a " + raw) is not None
            changed |= self.add({"k": "web-" + str(a.get("id") or time.time_ns()), "t": int(a.get("time") or time.time()),
                                 "kind": "web", "name": by, "msg": text, "ok": ok})
        return changed

    def save(self):
        self.items = self.items[-CHAT_KEEP:]
        self.keys = {e.get("k") for e in self.items}
        tmp = CHAT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.items, fh, ensure_ascii=False)
        os.replace(tmp, CHAT_FILE)


# ---------- Server starten / stoppen / neu starten (Knöpfe in der Status-Karte, nur Admin) ----------
# Feste Regel: nie stoppen oder neu starten, solange Spieler online sind oder Simple Backups eine ZIP schreibt.
# Dann bleibt nur „sobald leer“ (mc-restart-when-empty [stop]) oder „Spieler fragen“ (mc-restart-vote).
def power_state(live):
    """Dienst-Zustand und geplante Aktion (wartet auf leeren Server / Spieler-Abfrage läuft)."""
    pend = None
    for line in sh("pgrep", "-af", "mc-restart-when-empty|mc-restart-vote").splitlines():
        if "mc-restart-vote" in line:
            pend = {"kind": "vote"}
            break
        if "mc-restart-when-empty" in line and "pgrep" not in line:
            pend = {"kind": "stop_empty" if line.rstrip().endswith(" stop") else "restart_empty"}
    busy = any(x.get("phase") == "erstellen" for x in (live.get("backup") or {}).get("active", []))
    return {"service": sh("systemctl", "is-active", "void-draconic") or "unknown", "pending": pend, "backup_busy": busy}


def power_actions(live, power):
    files = sorted(glob.glob(os.path.join(CONTROL, "power-*.json")))
    if not files:
        return
    log = read_json(ADMIN_LOG, [])
    for f in files:
        a = read_json(f, None) or {}
        try:
            os.remove(f)
        except OSError:
            pass
        act, svc = a.get("action"), power["service"]
        empty = not (live.get("players") or {}).get("online")
        res, ok = "", True
        if act == "start":
            if svc in ("active", "activating"):
                res, ok = "läuft schon", False
            else:
                sh("systemctl", "--no-block", "start", "void-draconic")
                res = "Server wird gestartet"
        elif act in ("stop", "restart"):
            if not empty:
                res, ok = "abgelehnt: Spieler online (Regel) – „sobald leer“ oder „Spieler fragen“ nutzen", False
            elif power["backup_busy"]:
                res, ok = "abgelehnt: Backup wird gerade geschrieben – „sobald leer“ wartet darauf", False
            else:
                # über mc-restart-when-empty: vorher ein Backup, falls das letzte älter als 2 Std. ist
                sh("systemd-run", "--unit=mc-power-%d" % int(time.time()), "/usr/local/bin/mc-restart-when-empty", *(["stop"] if act == "stop" else []))
                res = "Server wird gestoppt (vorher Backup, falls nötig)" if act == "stop" else "Server wird neu gestartet (vorher Backup, falls nötig)"
        elif act in ("stop_empty", "restart_empty", "restart_vote"):
            if power["pending"]:
                res, ok = "es ist schon eine Aktion geplant", False
            else:
                cmd = ["/usr/local/bin/mc-restart-vote"] if act == "restart_vote" else \
                      ["/usr/local/bin/mc-restart-when-empty"] + (["stop"] if act == "stop_empty" else [])
                sh("systemd-run", f"--unit=mc-dash-{act.replace('_', '-')}-{int(time.time())}", *cmd)
                res = {"stop_empty": "stoppt, sobald 60 s niemand online ist",
                       "restart_empty": "startet neu, sobald 60 s niemand online ist",
                       "restart_vote": "Spieler werden gefragt (alle müssen zustimmen)"}[act]
        elif act == "cancel":
            if (power["pending"] or {}).get("kind") in ("stop_empty", "restart_empty"):
                sh("pkill", "-f", "mc-restart-when-empty")
                res = "geplante Aktion abgebrochen"
            else:
                res, ok = "nichts abzubrechen (eine Spieler-Abfrage endet von selbst)", False
        else:
            continue
        print(f"Server-Knopf {act} durch {a.get('by')}: {res}", flush=True)
        log.append({**a, "player": "Server", "ok": ok, "result": res, "done": int(time.time())})
    save_admin_log(log)


# ---------- Pack-Updates: Server und Spieler-Clients gegen GitHub main ----------
# Kennung eines Pack-Stands ist der SHA-256 der pack.toml (packwiz.json: packFileHash). Die pack.toml enthält den
# Hash der index.toml, ändert sich also mit jeder Pack-Änderung. Der Server lädt beim Start main (start.sh), die
# Clients bei jedem Spielstart (Prism-PreLaunch). Die Clients melden ihren Stand per KubeJS (pack_report.js) nach vd-clients/.
REPO = "Bresqwik/void-draconic-pack"
PACK_DB = os.path.join(STATE, "pack-versions.json")    # {"order": [commit, …] neueste zuerst, "c": {commit: {...}}, "meta": {hash: {...}}}
CLIENTS_DIR = os.path.join(MC, "vd-clients")
SERVER_ONLY = ("kubejs/server_scripts/", "kubejs/data/", "defaultconfigs/", "config/ftbquests/")
CLIENT_ONLY = ("kubejs/client_scripts/", "kubejs/assets/", "resourcepacks/", "shaderpacks/", "config/fancymenu/",
               "config/drippyloadingscreen/", "options.txt")
UPDATES = {}    # fertiges Ergebnis für status.json (schreibt der Hintergrund-Thread)
_index = {}     # commit -> {pfad: (hash, metafile)}


def http(url, api=False):
    import urllib.request
    h = {"User-Agent": "vd-dashboard"}
    if api:
        h["Accept"] = "application/vnd.github+json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=8) as r:
            return r.read()
    except Exception:
        return None


def raw(commit, path):
    return http(f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}")


def pack_refresh(db):
    """Letzte 30 Commits von main holen und für neue Commits Hash + Version der pack.toml merken."""
    import hashlib
    data = http(f"https://api.github.com/repos/{REPO}/commits?sha=main&per_page=30", api=True)
    try:
        commits = json.loads(data) if data else []
    except ValueError:
        commits = []
    if not isinstance(commits, list) or not commits:
        return False
    for c in commits:
        sha = c.get("sha")
        if not sha or sha in db["c"]:
            continue
        pt = raw(sha, "pack.toml")
        if pt is None:
            continue
        m = re.search(rb'^version = "([^"]+)"', pt, re.M)
        when = (c.get("commit", {}).get("committer") or {}).get("date") or ""
        db["c"][sha] = {"hash": hashlib.sha256(pt).hexdigest(), "version": m.group(1).decode() if m else "?",
                        "msg": (c.get("commit", {}).get("message") or "").split("\n")[0][:160],
                        "t": calendar.timegm(time.strptime(when, "%Y-%m-%dT%H:%M:%SZ")) if when else 0}
    new = [c["sha"] for c in commits if c.get("sha") in db["c"]]
    db["order"] = new + [s for s in db["order"] if s not in new]
    db["order"] = db["order"][:400]
    db["c"] = {s: db["c"][s] for s in db["order"] if s in db["c"]}
    return True


def index_of(commit):
    import tomllib
    if commit not in _index:
        t = raw(commit, "index.toml")
        if t is None:
            return None
        try:
            files = tomllib.loads(t.decode("utf-8")).get("files", [])
        except ValueError:
            return None
        if len(_index) > 8:
            _index.pop(next(iter(_index)))
        _index[commit] = {f["file"]: (f.get("hash"), bool(f.get("metafile"))) for f in files}
    return _index[commit]


def meta_of(db, commit, path, h):
    """Name, Seite und Dateiname einer Mod (.pw.toml), gemerkt nach Datei-Hash."""
    import tomllib
    if h not in db["meta"]:
        t = raw(commit, path)
        try:
            d = tomllib.loads(t.decode("utf-8")) if t else {}
        except ValueError:
            d = {}
        if not d:
            return {"name": os.path.basename(path).replace(".pw.toml", ""), "side": "both", "file": ""}
        db["meta"][h] = {"name": d.get("name") or path, "side": d.get("side") or "both", "file": d.get("filename") or ""}
    return db["meta"][h]


def pack_diff(db, old, new):
    """Was ändert sich von Commit old zu Commit new? Liste mit Art, Name, Seite (client/server/both)."""
    a, b = index_of(old), index_of(new)
    if a is None or b is None:
        return None
    out = []
    for p in sorted(set(a) | set(b)):
        ha, hb = a.get(p, (None, False))[0], b.get(p, (None, False))[0]
        if ha == hb:
            continue
        kind = "neu" if ha is None else "entfernt" if hb is None else "geändert"
        meta = (b if hb else a)[p][1]
        if meta:
            mb = meta_of(db, new, p, hb) if hb else None
            ma = meta_of(db, old, p, ha) if ha else None
            m = mb or ma
            out.append({"kind": kind, "mod": True, "name": m["name"], "side": m["side"], "path": p,
                        "from": (ma or {}).get("file", ""), "to": (mb or {}).get("file", "")})
        else:
            side = "server" if p.startswith(SERVER_ONLY) else "client" if p.startswith(CLIENT_ONLY) else "both"
            out.append({"kind": kind, "mod": False, "name": p, "side": side, "path": p})
    return out


def summarize(changes, side):
    """Änderungen für eine Seite (server/client): Mods einzeln, sonstige Dateien nach Ordner gezählt."""
    rel = [c for c in changes if c["side"] in ("both", side)]
    mods = [{k: c[k] for k in ("kind", "name", "from", "to")} for c in rel if c["mod"]]
    folders = {}
    for c in rel:
        if not c["mod"]:
            top = "/".join(c["path"].split("/")[:2]) if c["path"].startswith("kubejs/") else c["path"].split("/")[0]
            folders[top] = folders.get(top, 0) + 1
    return {"count": len(rel), "mods": mods, "files": [{"dir": k, "n": v} for k, v in sorted(folders.items(), key=lambda x: -x[1])]}


def commit_for(db, h):
    return next((s for s in db["order"] if db["c"][s]["hash"] == h), None)


def ver(db, commit):
    c = db["c"].get(commit) or {}
    return {"commit": commit[:7] if commit else None, "version": c.get("version"), "t": c.get("t"), "hash": c.get("hash")}


def pack_commits(db, old, new):
    """Commit-Meldungen von old (exklusiv) bis new, neueste zuerst; ohne Merges und ohne Commits, die das Pack nicht
    ändern. GitHub-Vergleich (1 Anfrage je neuem Stand, gemerkt), sonst Näherung über die Reihenfolge."""
    key = old + ".." + new
    cmp = db.setdefault("cmp", {})
    if key not in cmp:
        data = http(f"https://api.github.com/repos/{REPO}/compare/{old}...{new}", api=True)
        try:
            commits = json.loads(data).get("commits") if data else None
        except (ValueError, AttributeError):
            commits = None
        if commits is None:
            return []
        out = []
        for c in reversed(commits):
            parents = [x.get("sha") for x in c.get("parents", [])]
            if len(parents) > 1:
                continue
            me, par = db["c"].get(c["sha"]), db["c"].get(parents[0]) if parents else None
            if me and par and me["hash"] == par["hash"]:
                continue
            when = (c.get("commit", {}).get("committer") or {}).get("date") or ""
            out.append({"commit": c["sha"][:7], "msg": (c.get("commit", {}).get("message") or "").split("\n")[0][:160],
                        "t": calendar.timegm(time.strptime(when, "%Y-%m-%dT%H:%M:%SZ")) if when else 0,
                        "version": (me or {}).get("version")})
        cmp[key] = out[:20]
        for k in list(cmp)[:-6]:
            cmp.pop(k)
    return cmp[key]


def pack_updates(db, online):
    main_c = db["order"][0] if db["order"] else None
    if not main_c:
        return {"error": "GitHub nicht erreichbar"}
    main_h = db["c"][main_c]["hash"]
    sw = read_json(os.path.join(MC, "packwiz.json"), {})
    server_h = ((sw.get("packFileHash") or {}).get("value"))
    server_c = commit_for(db, server_h)
    res = {"time": int(time.time()), "main": ver(db, main_c), "server": {**ver(db, server_c), "hash": server_h, "current": False}}
    if server_h == main_h:
        res["server"]["current"] = True
    elif server_c:
        ch = pack_diff(db, server_c, main_c)
        if ch is not None:
            res["server"].update(current=False, changes=summarize(ch, "server"), client_changes=summarize(ch, "client"),
                                 commits=pack_commits(db, server_c, main_c))
    else:
        res["server"]["unknown"] = True
    # Spieler-Clients: Meldungen der letzten 7 Tage, dazu alle Online-Spieler (auch ohne Meldung)
    reports = {}
    for f in glob.glob(os.path.join(CLIENTS_DIR, "*.json")):
        r = read_json(f, None)
        if isinstance(r, dict) and r.get("name"):
            reports[r["name"]] = r
    clients = []
    for name in sorted(set(online) | {n for n, r in reports.items() if time.time() - r.get("time", 0) / 1000 < 7 * 86400}, key=str.lower):
        r = reports.get(name)
        e = {"name": name, "online": name in online}
        if not r or not r.get("hash"):
            e["state"] = "unbekannt"
        else:
            cc = commit_for(db, r["hash"])
            e.update(seen=int(r.get("time", 0) / 1000), **{k: v for k, v in ver(db, cc).items() if k != "hash"})
            if r["hash"] == main_h:
                e["state"] = "aktuell"
            elif not cc:
                e["state"] = "fremd"
            else:
                ch = pack_diff(db, cc, main_c)
                need = summarize(ch, "client") if ch is not None else None
                e["state"] = "neustart" if need and need["count"] else "ok"
                if need:
                    e["changes"] = need
                if server_c and r["hash"] != server_h:
                    chs = pack_diff(db, cc, server_c)
                    e["behind_server"] = bool(chs and summarize(chs, "client")["count"])
        clients.append(e)
    res["clients"] = clients
    return res


def pack_worker(get_online):
    """Hintergrund-Thread: alle 5 Min. GitHub fragen, jede Minute Server- und Client-Stand neu bewerten."""
    global UPDATES
    db = read_json(PACK_DB, None) or {}
    db.setdefault("order", []); db.setdefault("c", {}); db.setdefault("meta", {})
    last = 0
    while True:
        try:
            if time.time() - last > 300:
                last = time.time()  # auch bei Fehlschlag erst in 5 Min. wieder (GitHub erlaubt 60 Anfragen/Std.)
                if not pack_refresh(db):
                    raise RuntimeError("GitHub nicht erreichbar")
                tmp = PACK_DB + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(db, fh, ensure_ascii=False)
                os.replace(tmp, PACK_DB)
            UPDATES = pack_updates(db, get_online())
        except Exception as e:
            print("Pack-Updates:", type(e).__name__, e, flush=True)
        time.sleep(60)


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
    pregen_log = {}  # nur Log-Stand, für den Wächter (gespeicherte Aufträge könnten alt sein)
    pg_now = None    # laufende Generierung (Welt, Chunks/s, Prozent, Restzeit) für die CPS-Anzeige
    pdetails, last_details = {}, 0  # Online-Spieler: Dimension, Position, Leben … (alle 10 s)
    loop = "--once" not in sys.argv
    online_now = []
    chat = Chat()
    if loop:
        threading.Thread(target=pack_worker, args=(lambda: list(online_now),), daemon=True).start()
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
        tps = parse_tps(RCON.cmd("forge tps")) if live["online"] else None
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
        job = GUARD.tick(now, live, pregen_log)
        # LEAVE_BACKUP.tick(now, live)  # aus seit 19.10.2026: nur noch 1 Backup pro Tag (04:00) – Stefan, „keine doppelten Backups“
        watch = GUARD.watch()
        if job.get("active"):
            live["pregen_job"] = {"radius": job.get("radius"), "world": job.get("world"), "label": job.get("label"), "state": GUARD.state,
                                  "waiting": bool(GUARD.empty_since) and GUARD.state != "running" and not (live["players"]["online"] and watch)}
        live["pregen"] = {"watch": watch, "queue": read_json(QUEUE, []), "history": read_json(DONE, [])[-6:],
                          "plan": read_json(os.path.join(CONTROL, "pregen-plan.json"), None),
                          "stopped": None if job.get("active") else read_json(os.path.join(STATE, "pregen-job.gestoppt.json"), None),
                          "queue_stopped": read_json(os.path.join(STATE, "pregen-queue.gestoppt.json"), []),
                          "active": bool(job.get("active")), "state": GUARD.state, "brake": job.get("brake")}
        live["backup"] = backup_live(now)
        live["pregen_now"] = pg_now
        # Online seit: erste Sichtung je Sitzung, übersteht Neustarts des Sammlers (cache)
        sess = cache.setdefault("sessions", {})
        names_now = live["players"]["names"]
        for n in names_now:
            sess.setdefault(n, now)
        for n in [n for n in sess if n not in names_now]:
            sess.pop(n)
        if live["online"] and names_now and now - last_details >= 10:
            pdetails, last_details = player_details(names_now), now
        online_now[:] = names_now
        live["players"]["details"] = {n: {**pdetails.get(n, {}), "since": sess.get(n)} for n in names_now}
        if live["online"]:
            player_actions(level)
        live["power"] = power_state(live)
        power_actions(live, live["power"])
        if chat.post(live["online"]) | chat.read_log():
            chat.save()
        live["chat"] = chat.items[-CHAT_SHOW:]
        lag_reports(live)
        lag_actions()
        live["lag_reports"] = read_json(LAG_LOG, [])[-10:]
        arch = read_json(LAG_ARCHIVE, [])
        live["lag_archive"] = {"total": len(arch), "items": arch[-30:]}
        meld_reports()
        lag_actions("meld", MELD_LOG, MELD_ARCHIVE)
        live["meld_reports"] = read_json(MELD_LOG, [])[-20:]
        arch = read_json(MELD_ARCHIVE, [])
        live["meld_archive"] = {"total": len(arch), "items": arch[-30:]}
        live["claims"] = claims_data()
        live["ma"] = ma_progress()
        live["sprung"] = sprung_data()
        afk = (read_json(os.path.join(MC, "vd-afk.json"), {}) or {}).get("players") or {}
        live["afk"] = {n: v for n, v in afk.items() if n in (live.get("players") or {}).get("names", [])}
        write_json("live.json", live)

        # --- alle 30 s ---
        if now - last_slow >= SLOW_EVERY or not loop:
            last_slow = now
            text = read_log_tail()
            names, _ = known_names()
            if UPDATES.get("main", {}).get("version"):  # kommt vom Hintergrund-Thread (pack_worker)
                cache["pack_version"], cache["pack_t"] = UPDATES["main"]["version"], now
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
            global WORLD_BYTES
            WORLD_BYTES = (cache.get("world") or {}).get("overworld") or 0
            du = os.statvfs("/")
            # Stand je Dimension: gespeicherte Chunky-Aufträge, darüber die aktuellen Log-Zeilen (laufender Auftrag)
            tasks = chunky_tasks()
            pregen = {w: dict(v) for w, v in tasks.items()}
            pregen_log = chunky_progress(text)
            pg_now = next(({"world": w, "rate": v.get("rate"), "percent": v.get("percent"), "eta": v.get("eta"), "chunks": v.get("chunks"),
                            "t": now} for w, v in pregen_log.items() if v.get("state") == "running"), None)
            for w, v in pregen_log.items():
                pregen.setdefault(w, {}).update(v)
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
                         "minecraft": live.get("version") or "1.20.1", "loader": "Forge 47.4.26"},
                "game": {"time": game_time() if live["online"] else None, "weather": weather(level), "entities": dims},
                "world": {"size": cache.get("world", {}), "size_time": cache.get("world_t"), "pregen": pregen,
                          "radius": {**RADIUS_DEFAULT, **{w: v["radius"] for w, v in tasks.items() if v.get("radius")},
                                     **({GUARD.job().get("world", "minecraft:overworld"): GUARD.job()["radius"]} if GUARD.job().get("radius") else {})}},
                "backups": backups(),
                "updates": UPDATES,
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
            avg["cps"] = pg_now["rate"] if pg_now and pg_now.get("rate") is not None else None
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
