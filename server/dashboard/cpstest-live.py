#!/usr/bin/env python3
"""Live-Daten der CPS-Testbank (/opt/vd-cps-test) für die Dashboard-Seite cpstest.html.
Schreibt alle 2 Sekunden /var/www/mc-dashboard/data/cpstest.json: Chunky-Fortschritt, Chunks/s, MSPT,
CPU je Kern, Java-Last und RAM, dazu die Ergebnisse aller Testläufe (results/*.json).
Läuft als Dienst vd-cpstest-live (root), solange die Testbank gebraucht wird."""
import glob, json, os, re, socket, struct, time

BASE = "/opt/vd-cps-test"
OUT = "/var/www/mc-dashboard/data/cpstest.json"
PLAN = [("baseline", "Baseline", "Pack wie live (Noisium, Canary)"),
        ("byepregen", "ByePregen", "+ ByePregen 1.1.2.3, ohne Noisium"),
        ("byepregen_fastnoise", "ByePregen + Fast Noise", "+ ByePregen + Fast Noise 1.0.13"),
        ("c2me", "C2ME-Port (Makki132)", "+ c2meforge 0.2.0-forge.9.8"),
        ("c2me_8t", "C2ME, 8 Threads, 12 Kerne", "C2ME mit 8 Worldgen-Threads, Server auf allen 12 Kernen (8/4-Split)"),
        ("lang_ow", "Langzeit: Oberwelt r1.500", "C2ME 8 Threads · 35 721 Chunks"),
        ("lang_nether", "Langzeit: Nether r1.000", "C2ME 8 Threads · 16 129 Chunks"),
        ("lang_tf", "Langzeit: Twilight Forest r750", "C2ME 8 Threads · 9 409 Chunks")]
REFERENCE = {"name": "referenz", "label": "Referenz 09.10. (Live-Server)", "cps": 4.6}


def props():
    try:
        return dict(l.split("=", 1) for l in open(os.path.join(BASE, "server.properties")).read().splitlines()
                    if "=" in l and not l.startswith("#"))
    except OSError:
        return {}


class Rcon:
    def __init__(self):
        self.s = None

    def cmd(self, c):
        for _ in range(2):
            try:
                if not self.s:
                    p = props()
                    self.s = socket.create_connection(("127.0.0.1", int(p.get("rcon.port", 25611))), timeout=5)
                    self._send(1, 3, p.get("rcon.password", ""))
                    if self._recv()[0] == -1:
                        raise OSError("auth")
                self._send(2, 2, c)
                return re.sub("§.", "", self._recv()[1])
            except (OSError, struct.error, ValueError):
                self.close()
        return None

    def _send(self, rid, typ, body):
        b = body.encode()
        self.s.sendall(struct.pack("<iii", len(b) + 10, rid, typ) + b + b"\0\0")

    def _recv(self):
        n = struct.unpack("<i", self._read(4))[0]
        d = self._read(n)
        return struct.unpack("<i", d[:4])[0], d[8:-2].decode("utf-8", "replace")

    def _read(self, n):
        d = b""
        while len(d) < n:
            c = self.s.recv(n - len(d))
            if not c:
                raise OSError("closed")
            d += c
        return d

    def close(self):
        try:
            self.s and self.s.close()
        except OSError:
            pass
        self.s = None


def cpu_times():
    cores = {}
    for line in open("/proc/stat"):
        m = re.match(r"cpu(\d+) (.*)", line)
        if m:
            v = [int(x) for x in m.group(2).split()]
            cores[int(m.group(1))] = (sum(v), v[3] + v[4])  # gesamt, idle+iowait
    return cores


def java_pid():
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if os.readlink(d + "/cwd") == BASE and open(d + "/comm").read().strip() == "java":
                return int(d[6:])
        except OSError:
            pass
    return None


def proc_ticks(pid):
    """CPU-Zeit des Prozesses (utime + stime) in Takten."""
    try:
        f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
        return int(f[11]) + int(f[12])
    except (OSError, IndexError):
        return None


def rss_mb(pid):
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024)
    except OSError:
        pass
    return None


def results():
    out = {}
    for f in glob.glob(os.path.join(BASE, "results", "*.json")):
        try:
            out[os.path.basename(f)[:-5]] = json.load(open(f))
        except (OSError, ValueError):
            pass
    return out


JCMD = "/usr/lib/jvm/temurin-17-jdk-amd64/bin/jcmd"
INTEREST = re.compile(r"c2me|byepregen|fastnoise|noisium|canary|chunky|modernfix|lithostitched|tectonic|terralith", re.I)
LOGPAT = re.compile(r"\[Chunky\]|c2me|C2ME|Exception|/ERROR\]|Can't keep up|OutOfMemory")
NOISE = re.compile(r"GenericMethod|RuntimeDistCleaner|Couldn't fully analyze|mixin/\]|^\s+at ")


def heap(pid):
    """Java-Heap belegt/gesamt in MB (jcmd GC.heap_info)."""
    import subprocess
    try:
        out = subprocess.run(["sudo", "-u", "minecraft", JCMD, str(pid), "GC.heap_info"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"heap\s+total (\d+)K, used (\d+)K", out)
        return (round(int(m.group(2)) / 1024), round(int(m.group(1)) / 1024)) if m else (None, None)
    except Exception:
        return None, None


def dir_size(path):
    total = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def sysinfo():
    info = {}
    try:
        info["load"] = [float(x) for x in open("/proc/loadavg").read().split()[:3]]
        mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo") if ":" in l}
        info["mem_total_mb"] = round(mem["MemTotal"] / 1024)
        info["mem_avail_mb"] = round(mem["MemAvailable"] / 1024)
    except (OSError, KeyError, ValueError):
        pass
    return info


def c2me_conf():
    try:
        t = open(os.path.join(BASE, "config", "c2me.toml")).read()
        m = re.search(r'^globalExecutorParallelism\s*=\s*"?([^"\n]+)"?', t, re.M)
        return m.group(1).strip() if m else None
    except OSError:
        return None


def log_events(since_line):
    """Zählt Warnungen/Fehler und liefert die letzten interessanten Zeilen des aktuellen Testlaufs."""
    try:
        lines = open(os.path.join(BASE, "logs", "latest.log"), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return {}
    warn = sum(1 for l in lines if "/WARN]" in l)
    err = sum(1 for l in lines if "/ERROR]" in l and not NOISE.search(l))
    pick = [l for l in lines if LOGPAT.search(l) and not NOISE.search(l) and "Task running" not in l][-8:]
    out = []
    for l in pick:
        m = re.match(r"\[[^ ]+ ([\d:]+)\.\d+\] \[([^/\]]+)/(\w+)\] \[[^\]]*\]: (.*)", l)
        out.append({"t": m.group(1), "lvl": m.group(3), "msg": m.group(4)[:180]} if m else {"t": "", "lvl": "", "msg": l[:180]})
    return {"warn": warn, "err": err, "lines": out, "total": len(lines)}


def bench_cpus():
    """CPU-Kerne des Testservers aus run-bench.sh (taskset -c …)."""
    try:
        m = re.search(r"taskset -c ([\d,-]+)", open(os.path.join(BASE, "run-bench.sh")).read())
        return m.group(1) if m else None
    except OSError:
        return None


def main():
    rcon = Rcon()
    hz = os.sysconf("SC_CLK_TCK")
    prev_cores, prev_proc, prev_t = cpu_times(), None, time.time()
    hist = []  # [t, cps, cpu_kerne, mspt]
    last_chunks, last_chunks_t = None, None
    slow, slow_t, trail, trail_world = {}, 0, [], None
    size_hist = []  # [t, bytes]
    while True:
        time.sleep(1)
        now = time.time()
        cores = cpu_times()
        core_use = {c: round(100 * (1 - (cores[c][1] - prev_cores[c][1]) / max(1, cores[c][0] - prev_cores[c][0])), 1)
                    for c in cores if c in prev_cores}
        prev_cores = cores
        pid = java_pid()
        cpu_kerne = rss = None
        if pid:
            ticks = proc_ticks(pid)
            if ticks is not None and prev_proc and prev_proc[0] == pid:
                cpu_kerne = round((ticks - prev_proc[1]) / hz / max(0.5, now - prev_t), 2)
            prev_proc = (pid, ticks) if ticks is not None else None
            rss = rss_mb(pid)
        else:
            prev_proc = None
            rcon.close()
        prev_t = now
        world = props().get("level-name", "")
        try:
            current = json.load(open(os.path.join(BASE, "results", "_current.json")))
        except (OSError, ValueError):
            current = None
        active = (current or {}).get("name") or (world[6:] if world.startswith("world_") else world)
        live = {"server": "aus" if not pid else "startet", "world": world, "active": active}
        if pid:
            prog = rcon.cmd("chunky progress")
            if prog is not None:
                live["server"] = "läuft"
                m = re.search(r"Processed: (\d+) chunks \(([\d,]+)%\), ETA: ([\d:]+), Rate: ([\d,]+) cps", prog)
                if m:
                    chunks = int(m.group(1))
                    # eigene CPS aus der Chunk-Differenz (Chunky glättet über längere Zeit)
                    inst = None
                    if last_chunks is not None and chunks >= last_chunks and now > last_chunks_t:
                        inst = round((chunks - last_chunks) / (now - last_chunks_t), 2)
                    last_chunks, last_chunks_t = chunks, now
                    live.update(task=True, chunks=chunks, percent=float(m.group(2).replace(",", ".")), eta=m.group(3),
                                rate=float(m.group(4).replace(",", ".")), cps_now=inst)
                    pos = re.search(r"Current: (-?\d+), (-?\d+)", prog)
                    if pos:
                        live["pos"] = [int(pos.group(1)), int(pos.group(2))]
                        if trail_world != world:
                            trail, trail_world = [], world
                        trail.append(live["pos"])
                        trail = trail[-1500:]
                else:
                    live["task"] = False
                    last_chunks = None
                cur_dim = (current or {}).get("dim", "minecraft:overworld")
                tps = rcon.cmd(f"forge tps {cur_dim}") or ""
                m = re.search(r"Mean tick time: ([\d.,]+) ms", tps)
                if m:
                    live["mspt"] = float(m.group(1).replace(",", "."))
        live.update(cpu_kerne=cpu_kerne, rss_mb=rss, cores=core_use)
        # langsamere Werte alle 10 s: Heap, Weltgröße, Log, Konfiguration
        if now - slow_t >= 10:
            slow_t = now
            slow = {"sys": sysinfo(), "c2me_threads": c2me_conf(),
                    "mods": sorted(f for f in os.listdir(os.path.join(BASE, "mods")) if INTEREST.search(f)) if os.path.isdir(os.path.join(BASE, "mods")) else [],
                    "log": log_events(0) if pid else {}}
            if pid:
                slow["heap_used_mb"], slow["heap_total_mb"] = heap(pid)
            wdir = os.path.join(BASE, world, "region")
            if os.path.isdir(wdir):
                size = dir_size(wdir)
                size_hist.append([int(now), size])
                size_hist = [s for s in size_hist if s[0] > now - 300]
                slow["region_mb"] = round(size / 1048576, 1)
                if len(size_hist) > 1 and size_hist[-1][0] > size_hist[0][0]:
                    slow["region_mb_min"] = round((size_hist[-1][1] - size_hist[0][1]) / 1048576 / ((size_hist[-1][0] - size_hist[0][0]) / 60), 1)
        live.update(slow)
        live["trail"] = trail if trail_world == world else []
        hist.append([int(now), live.get("cps_now"), cpu_kerne, live.get("mspt")])
        hist = [h for h in hist if h[0] > now - 1800][-1800:]
        res = results()
        runs = []
        for name, label, mods in PLAN:
            r = res.get(name) or {}
            st = "fertig" if r.get("cps") else ("läuft" if name == active and pid else ("abgebrochen" if r.get("error") else "geplant"))
            runs.append({"name": name, "label": label, "mods": mods, "status": st, "cps": r.get("cps"), "mspt": r.get("mspt_mean"),
                         "time": r.get("chunky_time"), "percent": 100 if st == "fertig" else (live.get("percent") if st == "läuft" else 0)})
        data = {"t": int(now), "live": live, "hist": hist, "runs": runs, "reference": REFERENCE,
                "cpus_test": bench_cpus(), "ncpu": len(cores), "current": current or {"radius": 400, "center_chunk": [1250, 1250], "side": 51, "total": 2601, "dim": "minecraft:overworld"},
                "xmx": "12G", "seed": "5042199124780357457"}
        tmp = OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
