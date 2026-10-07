#!/usr/bin/env python3
"""Void & Draconic Dashboard – Datensammler.

Läuft jede Minute (systemd-Timer mc-dashboard.timer) und schreibt JSON-Dateien,
die die Dashboard-Seite anzeigt:
  status.json   Live-Status: Server, Spieler, TPS, System, Welt, Backups
  history.json  Verlauf: 24 h minütlich, 7 Tage in 10-Minuten-Schritten
  players.json  Statistiken pro Spieler aus world/stats und world/advancements

Nur Python-Standardbibliothek. TPS kommen per RCON (nur lokal, Port per ufw gesperrt).
"""
import glob, json, os, re, socket, struct, subprocess, time

MC = "/opt/void-draconic"
OUT = "/var/www/mc-dashboard/data"
STATE = "/var/lib/mc-dashboard"
HIST = os.path.join(STATE, "history.jsonl")
CACHE = os.path.join(STATE, "cache.json")
NOW = int(time.time())


def write_json(name, data):
    tmp = os.path.join(OUT, "." + name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(OUT, name))


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
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
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
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
    """Text-Komponente der MOTD in reinen Text umwandeln."""
    if isinstance(desc, str):
        return re.sub("§.", "", desc)
    if isinstance(desc, list):
        return "".join(plain(d) for d in desc)
    if isinstance(desc, dict):
        return plain(desc.get("text", "")) + "".join(plain(e) for e in desc.get("extra", []))
    return ""


# ---------- RCON (nur 127.0.0.1) ----------
def rcon(cmd, p):
    if p.get("enable-rcon") != "true" or not p.get("rcon.password"):
        return None
    try:
        with socket.create_connection(("127.0.0.1", int(p.get("rcon.port", 25575))), timeout=5) as s:
            def send(rid, typ, body):
                b = body.encode("utf-8")
                s.sendall(struct.pack("<iii", len(b) + 10, rid, typ) + b + b"\x00\x00")

            def recv():
                ln = struct.unpack("<i", s.recv(4))[0]
                d = b""
                while len(d) < ln:
                    d += s.recv(ln - len(d))
                rid, typ = struct.unpack("<ii", d[:8])
                return rid, d[8:-2].decode("utf-8", "replace")

            send(1, 3, p["rcon.password"])
            if recv()[0] == -1:
                return None
            send(2, 2, cmd)
            return recv()[1]
    except Exception:
        return None


def parse_tps(text):
    """Ausgabe von /neoforge tps: pro Dimension mittlere Tickzeit (ms) und TPS."""
    res = {"dims": {}}
    if not text:
        return None
    for line in re.split(r"\n|(?=(?:Overall|[a-z0-9_.-]+:[a-z0-9_/.-]+)\s*:)", re.sub("§.", "", text)):
        m_ms = re.search(r"([\d.]+)\s*ms", line)
        m_tps = re.search(r"TPS[^\d]*([\d.]+)|([\d.]+)\s*TPS", line)
        if not (m_ms or m_tps):
            continue
        ms = float(m_ms.group(1)) if m_ms else None
        tps = float(next(g for g in m_tps.groups() if g)) if m_tps else (min(20.0, 1000 / ms) if ms else None)
        name = "overall" if line.strip().lower().startswith("overall") else (re.match(r"\s*([a-z0-9_.-]+:[a-z0-9_/.-]+)", line) or [None, None])[1]
        if name == "overall":
            res["tps"], res["mspt"] = tps, ms
        elif name:
            res["dims"][name] = {"tps": tps, "mspt": ms}
    return res if "tps" in res or res["dims"] else None


# ---------- System ----------
def cpu_percent():
    def snap():
        v = list(map(int, open("/proc/stat").readline().split()[1:]))
        idle = v[3] + v[4]
        return sum(v), idle
    t1, i1 = snap()
    time.sleep(1)
    t2, i2 = snap()
    return round(100 * (1 - (i2 - i1) / max(1, t2 - t1)), 1)


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


# ---------- Welt ----------
def chunky_progress():
    path = os.path.join(MC, "logs", "latest.log")
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 3_000_000))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return {}
    res = {}
    for m in re.finditer(r"\[Chunky\] Task (running|finished|stopped|paused) for ([a-z0-9_:]+)\.?(?: Processed: (\d+) chunks \(([\d.,]+)%\))?(?:, ETA: ([\d:]+))?(?:, Rate: ([\d.,]+) cps)?(?:, Total time: ([\d:]+))?", text):
        st, dim, n, pct, eta, rate, total = m.groups()
        cur = res.setdefault(dim, {})
        cur["state"] = st
        if n:
            cur["chunks"] = int(n)
        if pct:
            cur["percent"] = float(pct.replace(",", "."))
        if eta:
            cur["eta"] = eta
        if rate:
            cur["rate"] = float(rate.replace(",", "."))
        if total:
            cur["total_time"] = total
        if st == "finished":
            cur["percent"] = 100.0
    return res


def dir_size(path):
    out = sh("du", "-sb", path)
    return int(out.split()[0]) if out else None


# ---------- Backups ----------
def backups():
    files = []
    for f in glob.glob(os.path.join(MC, "simplebackups", "**", "*.zip"), recursive=True):
        st = os.stat(f)
        files.append({"name": os.path.basename(f), "size": st.st_size, "time": int(st.st_mtime)})
    files.sort(key=lambda x: x["time"], reverse=True)
    show = lambda u, p: sh("systemctl", "show", u, "-p", p, "--value", "--timestamp=unix")
    last = show("mc-backup-cloud.service", "ExecMainExitTimestamp")
    nxt = sh("date", "-d", show("mc-backup-cloud.timer", "NextElapseUSecRealtime"), "+@%s")
    log = sh("journalctl", "-u", "mc-backup-cloud.service", "-n", "5", "--no-pager", "-o", "cat")
    return {
        "local": files[:5],
        "cloud": {
            "last_run": int(last.lstrip("@")) if last.startswith("@") else None,
            "result": (show("mc-backup-cloud.service", "Result") or None) if last.startswith("@") else None,
            "next_run": int(nxt.lstrip("@")) if nxt.startswith("@") else None,
            "message": (log.splitlines() or [""])[-1][:200],
            "target": "Google Drive · Minecraft Modpack - Void & Draconic/Backups",
        },
    }


# ---------- Spieler ----------
CUSTOM = {
    "play_time": "minecraft:play_time", "deaths": "minecraft:deaths", "mob_kills": "minecraft:mob_kills",
    "player_kills": "minecraft:player_kills", "jumps": "minecraft:jump", "damage_dealt": "minecraft:damage_dealt",
    "damage_taken": "minecraft:damage_taken", "sleep": "minecraft:sleep_in_bed", "leave_game": "minecraft:leave_game",
}
DIST = {"walk": ["walk_one_cm", "sprint_one_cm", "crouch_one_cm", "walk_on_water_one_cm", "walk_under_water_one_cm"],
        "fly": ["fly_one_cm", "aviate_one_cm"], "swim": ["swim_one_cm"],
        "ride": ["boat_one_cm", "horse_one_cm", "minecart_one_cm", "pig_one_cm", "strider_one_cm"],
        "climb": ["climb_one_cm"], "fall": ["fall_one_cm"]}


def players(online_names):
    names = {}
    for fn in ("usercache.json", "whitelist.json"):
        try:
            for e in json.load(open(os.path.join(MC, fn), encoding="utf-8")):
                names[e["uuid"]] = e["name"]
        except (OSError, ValueError):
            pass
    wl = []
    try:
        wl = [e["uuid"] for e in json.load(open(os.path.join(MC, "whitelist.json"), encoding="utf-8"))]
    except (OSError, ValueError):
        pass
    level = props().get("level-name", "world")
    uuids = set(wl)
    uuids |= {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(MC, level, "stats", "*.json"))}
    online_lower = {n.lower() for n in online_names}
    out = []
    for u in sorted(uuids):
        name = names.get(u, u[:8])
        rec = {"uuid": u, "name": name, "online": name.lower() in online_lower, "whitelisted": u in wl}
        try:
            st = json.load(open(os.path.join(MC, level, "stats", u + ".json"), encoding="utf-8"))["stats"]
            cu = st.get("minecraft:custom", {})
            for k, key in CUSTOM.items():
                rec[k] = cu.get(key, 0)
            rec["play_time"] = rec["play_time"] // 20  # Ticks -> Sekunden
            rec["dist"] = {k: round(sum(cu.get("minecraft:" + x, 0) for x in v) / 100) for k, v in DIST.items()}  # Meter
            rec["mined"] = sum(st.get("minecraft:mined", {}).values())
            rec["crafted"] = sum(st.get("minecraft:crafted", {}).values())
            rec["placed"] = sum(st.get("minecraft:used", {}).get(k, 0) for k in st.get("minecraft:used", {}) if not k.endswith(("_sword", "_pickaxe", "_axe", "_shovel", "_hoe", "bow")))
            top = sorted(st.get("minecraft:killed", {}).items(), key=lambda x: -x[1])[:3]
            rec["top_kills"] = [[k.split(":")[-1], v] for k, v in top]
            top = sorted(st.get("minecraft:mined", {}).items(), key=lambda x: -x[1])[:3]
            rec["top_mined"] = [[k, v] for k, v in top]
            rec["last_seen"] = int(os.path.getmtime(os.path.join(MC, level, "stats", u + ".json")))
        except (OSError, ValueError, KeyError):
            rec["play_time"] = 0
        try:
            adv = json.load(open(os.path.join(MC, level, "advancements", u + ".json"), encoding="utf-8"))
            done = [k for k, v in adv.items() if isinstance(v, dict) and v.get("done") and "recipes/" not in k]
            rec["advancements"] = sum(1 for k in done if k.startswith("minecraft:"))
            rec["advancements_mods"] = len(done) - rec["advancements"]
        except (OSError, ValueError):
            rec["advancements"] = rec["advancements_mods"] = 0
        pd = os.path.join(MC, level, "playerdata", u + ".dat")
        if os.path.exists(pd):
            rec["last_seen"] = max(rec.get("last_seen", 0), int(os.path.getmtime(pd)))
        out.append(rec)
    out.sort(key=lambda r: (-r["online"], -r.get("play_time", 0)))
    return out


# ---------- Verlauf ----------
def history(point):
    os.makedirs(STATE, exist_ok=True)
    with open(HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps(point, separators=(",", ":")) + "\n")
    rows = []
    for line in open(HIST, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r["t"] >= NOW - 7 * 86400:
            rows.append(r)
    if len(rows) > 7 * 1440 + 200 or NOW % 3600 < 60:  # gelegentlich kürzen
        with open(HIST + ".tmp", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, separators=(",", ":")) + "\n" for r in rows)
        os.replace(HIST + ".tmp", HIST)
    day = [r for r in rows if r["t"] >= NOW - 86400]
    week, bucket = [], {}
    for r in rows:
        b = r["t"] // 600 * 600
        bucket.setdefault(b, []).append(r)
    keys = ["p", "tps", "mspt", "cpu", "ram"]
    for b in sorted(bucket):
        rs = bucket[b]
        avg = {"t": b}
        for k in keys:
            vals = [r[k] for r in rs if r.get(k) is not None]
            avg[k] = round(sum(vals) / len(vals), 2) if vals else None
        avg["p"] = max((r.get("p") or 0) for r in rs)
        week.append(avg)
    return {"day": day, "week": week}


# ---------- Server-Beschreibung (MiniMOTD), Zeile 2 live ----------
MOTD = os.path.join(MC, "config", "MiniMOTD", "main.conf")
TAG = re.compile(r"<[^>]+>")


def motd_line(status):
    """Zeile 2: Spielerzahl (setzt MiniMOTD bei jedem Ping ein), dazu Status und Pack-Version."""
    pg = status.get("world", {}).get("pregen", {}).get("minecraft:overworld", {})
    tps = (status.get("tps") or {}).get("tps")
    if pg.get("state") == "running":
        mid = f"<#C77DFF>Welt entsteht <white>{int(pg.get('percent', 0)) // 5 * 5} %"
    elif tps is not None:
        col = "#46C35B" if tps >= 19.5 else "#F5D547" if tps >= 15 else "#E5484D"
        mid = f"<#3FD0E0>TPS <{col}>{min(20, round(tps))}"
    else:
        mid = "<#3FD0E0>Refined Storage 2"
    ver = (status.get("pack") or {}).get("version") or ""
    line = f"<#46C35B>● <white><online_players><gray>/<max_players> online <dark_gray>• {mid} <dark_gray>• <#F5D547>v{ver}"
    visible = len(TAG.sub("", line)) + 3  # + Spielerzahl "0/6", die MiniMOTD einsetzt
    return " " * max(0, round((300 - 5.5 * visible) / 2 / 4)) + line  # Breite der Serverliste ca. 300 px


def update_motd(status, p):
    try:
        conf = open(MOTD, encoding="utf-8").read()
    except OSError:
        return
    new = motd_line(status).replace("\\", "\\\\").replace('"', '\\"')
    out, n = re.subn(r'^(\s*line2=")(?:[^"\\]|\\.)*(")', lambda m: m.group(1) + new + m.group(2), conf, count=1, flags=re.M)
    if not n or out == conf:
        return
    open(MOTD, "w", encoding="utf-8").write(out)
    if rcon("minimotd reload", p) is None and status.get("online"):
        sh("sudo", "-u", "minecraft", "tmux", "send-keys", "-t", "mc", "minimotd reload", "Enter")


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(STATE, exist_ok=True)
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    p = props()
    port = int(p.get("server-port", 25565))

    status = {"time": NOW, "address": "mc-void-draconic.duckdns.org", "online": False}
    try:
        sl = ping(port)
        status.update(online=True, version=sl.get("version", {}).get("name"), motd=plain(sl.get("description")),
                      players={"online": sl.get("players", {}).get("online", 0), "max": sl.get("players", {}).get("max", 0),
                               "names": sorted(x.get("name", "") for x in sl.get("players", {}).get("sample", []) or [])})
    except Exception as e:
        status["error"] = type(e).__name__
        status["players"] = {"online": 0, "max": int(p.get("max-players", 0) or 0), "names": []}

    tps = parse_tps(rcon("neoforge tps", p)) if status["online"] else None
    if tps:
        status["tps"] = tps
    if status["online"] and status["players"]["online"] and not status["players"]["names"]:
        lst = rcon("list", p)
        if lst and ":" in lst:
            status["players"]["names"] = sorted(n.strip() for n in lst.split(":", 1)[1].split(",") if n.strip())

    mem = meminfo()
    pid = java_pid()
    du = os.statvfs("/")
    status["system"] = {
        "cpu": cpu_percent(), "cores": os.cpu_count(), "load": [round(x, 2) for x in os.getloadavg()],
        "ram_total": mem["MemTotal"], "ram_used": mem["MemTotal"] - mem["MemAvailable"],
        "java_rss": proc_rss(pid) if pid else None, "java_heap": "16 GB",
        "disk_total": du.f_blocks * du.f_frsize, "disk_used": (du.f_blocks - du.f_bfree) * du.f_frsize,
        "uptime": int(float(open("/proc/uptime").read().split()[0])),
        "mc_since": service_since("void-draconic.service"),
    }
    try:
        pack = open(os.path.join(MC, "packwiz.json"), encoding="utf-8").read()
        status["pack"] = {"mods": len(glob.glob(os.path.join(MC, "mods", "*.jar")))}
        m = re.search(r'version = "([^"]+)"', sh("curl", "-fsS", "-m", "5", "https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/pack.toml")) if NOW - cache.get("pack_t", 0) > 1800 else None
        if m:
            cache["pack_version"], cache["pack_t"] = m.group(1), NOW
        status["pack"]["version"] = cache.get("pack_version")
        del pack
    except OSError:
        pass

    level = p.get("level-name", "world")
    if NOW - cache.get("world_t", 0) > 600:
        cache["world"] = {d: dir_size(os.path.join(MC, level, *([] if d == "overworld" else [d])))
                          for d in ("overworld", "DIM-1", "DIM1")}
        cache["world_t"] = NOW
    status["world"] = {"seed_hidden": True, "size": cache.get("world", {}), "size_time": cache.get("world_t"),
                       "pregen": chunky_progress(), "radius": {"minecraft:overworld": 5000, "minecraft:the_nether": 2000, "minecraft:the_end": 2000}}
    status["backups"] = backups()

    point = {"t": NOW // 60 * 60, "p": status["players"]["online"], "tps": (tps or {}).get("tps"),
             "mspt": (tps or {}).get("mspt"), "cpu": status["system"]["cpu"],
             "ram": round(status["system"]["ram_used"] / 2**30, 2)}
    write_json("history.json", history(point))
    if NOW - cache.get("players_t", 0) >= 240 or status["players"]["online"] != cache.get("players_n"):
        write_json("players.json", {"time": NOW, "players": players(status["players"]["names"])})
        cache["players_t"], cache["players_n"] = NOW, status["players"]["online"]
    write_json("status.json", status)
    update_motd(status, p)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
