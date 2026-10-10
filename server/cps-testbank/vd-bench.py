#!/usr/bin/env python3
"""CPS-Testbank: startet /opt/vd-cps-test mit einer frischen Welt, generiert per Chunky ein Quadrat in der Oberwelt
und misst Chunks/s und MSPT. Aufruf (als root): bench.py <name> [--radius 400] [--cpus 4-11] [--jvm "-Dx=y ..."] [--jfr]
Ergebnis: /opt/vd-cps-test/results/<name>.json. Mods für die Variante liegen vorher schon in mods/ (setzt der Aufrufer)."""
import argparse, json, os, re, secrets, socket, struct, subprocess, time

BASE = "/opt/vd-cps-test"
JAVA = "/usr/lib/jvm/temurin-17-jdk-amd64/bin/java"
ARGS = "libraries/net/minecraftforge/forge/1.20.1-47.4.26/unix_args.txt"
SEED = "5042199124780357457"
LOG = os.path.join(BASE, "logs", "latest.log")


class Rcon:
    def __init__(self, port, pw):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=30)
        self._send(1, 3, pw)
        self._recv()

    def _send(self, rid, typ, body):
        b = body.encode()
        self.s.sendall(struct.pack("<iii", len(b) + 10, rid, typ) + b + b"\0\0")

    def _recv(self):
        n = struct.unpack("<i", self._read(4))[0]
        d = self._read(n)
        return d[8:-2].decode("utf-8", "replace")

    def _read(self, n):
        d = b""
        while len(d) < n:
            c = self.s.recv(n - len(d))
            if not c:
                raise OSError("closed")
            d += c
        return d

    def cmd(self, c):
        self._send(2, 2, c)
        return self._recv()


def setprops(world, rport, pw):
    p = os.path.join(BASE, "server.properties")
    t = open(p, encoding="utf-8").read()
    for k, v in {"level-name": world, "level-seed": SEED, "server-port": "25610", "query.port": "25610", "enable-rcon": "true",
                 "rcon.port": str(rport), "rcon.password": pw, "white-list": "true", "enforce-whitelist": "true",
                 "enable-query": "false", "view-distance": "10", "simulation-distance": "8", "max-tick-time": "-1"}.items():
        t, n = re.subn(rf"(?m)^{re.escape(k)}=.*$", f"{k}={v}", t)
        if not n:
            t += f"\n{k}={v}"
    open(p, "w", encoding="utf-8").write(t)


def log_text():
    try:
        return open(LOG, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--radius", type=int, default=400)
    ap.add_argument("--cpus", default="4-11")
    ap.add_argument("--xmx", default="9G")
    ap.add_argument("--jvm", default="")
    ap.add_argument("--jfr", action="store_true")
    ap.add_argument("--center", default="20000 20000")
    ap.add_argument("--attach", action="store_true", help="laufenden Testserver nutzen (kein Start)")
    ap.add_argument("--dim", default="minecraft:overworld")
    ap.add_argument("--label", default=None)
    ap.add_argument("--keep", action="store_true", help="Server danach nicht stoppen")
    a = ap.parse_args()
    os.makedirs(os.path.join(BASE, "results"), exist_ok=True)
    world, pw, rport = f"world_{a.name}", secrets.token_hex(12), 25611
    if a.attach:
        props = dict(l.split("=", 1) for l in open(os.path.join(BASE, "server.properties")).read().splitlines() if "=" in l and not l.startswith("#"))
        pw, rport = props["rcon.password"], int(props["rcon.port"])
    else:
        setprops(world, rport, pw)
    jvm = [f"-Xms{a.xmx}", f"-Xmx{a.xmx}", "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
           "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC", "-XX:G1NewSizePercent=40", "-XX:G1MaxNewSizePercent=50",
           "-XX:G1HeapRegionSize=16M", "-XX:G1ReservePercent=15", "-XX:InitiatingHeapOccupancyPercent=20",
           "-Dchunky.maxWorkingCount=150", "-Dterminal.jline=false", "-Dterminal.ansi=true"] + a.jvm.split()
    cmd = ["taskset", "-c", a.cpus, "nice", "-n", "5", JAVA] + jvm + [f"@{ARGS}", "nogui"]
    sh = os.path.join(BASE, "run-bench.sh")
    # Ohne exec: Exit-Code landet in results/<name>.exit, das tmux-Fenster bleibt 30 s offen
    open(sh, "w").write("#!/bin/sh\ncd %s\n%s\necho $? > %s/results/%s.exit\nsleep 30\n" % (BASE, " ".join(cmd), BASE, a.name))
    os.chmod(sh, 0o755)
    t0 = time.time()
    if not a.attach:
        # gespeicherte Chunky-Aufträge (z. B. aus der Live-Kopie) würden "chunky start" blockieren
        subprocess.run(["rm", "-rf", os.path.join(BASE, "config", "chunky", "tasks")])
        subprocess.run(["chown", "-R", "minecraft:minecraft", BASE])
        subprocess.run(["sudo", "-u", "minecraft", "tmux", "kill-session", "-t", "cpstest"], stderr=subprocess.DEVNULL)
        time.sleep(3)
        # altes Log beiseitelegen, sonst gelten "Done (" / "Stopping server" des letzten Laufs
        if os.path.exists(LOG):
            os.replace(LOG, os.path.join(BASE, "logs", f"vorher-{int(t0)}.log"))
        subprocess.run(["sudo", "-u", "minecraft", "tmux", "new-session", "-d", "-s", "cpstest", sh], check=True)
    res = {"name": a.name, "dim": a.dim, "radius": a.radius, "cpus": a.cpus, "xmx": a.xmx, "jvm": a.jvm, "mods": sorted(m for m in os.listdir(os.path.join(BASE, "mods")) if re.search(r"c2me|byepregen|fastnoise|noisium|canary|adrenaline", m, re.I)),
           "started": int(t0)}
    # warten bis "Done (" oder Absturz
    while True:
        time.sleep(0 if a.attach else 5)
        t = log_text()
        if "Done (" in t:
            res["startup_s"] = round(time.time() - t0)
            break
        if time.time() - t0 > 900 or subprocess.run(["sudo", "-u", "minecraft", "tmux", "has-session", "-t", "cpstest"]).returncode:
            res["error"] = "Start fehlgeschlagen"
            res["log_tail"] = t[-3000:]
            json.dump(res, open(os.path.join(BASE, "results", a.name + ".json"), "w"), indent=1)
            print(json.dumps(res)[:3000])
            return
    # Test-JVM als erstes Opfer für den OOM-Killer markieren (Live-Server schützen)
    for p in subprocess.run(["pgrep", "-f", "Xmx" + a.xmx], capture_output=True, text=True).stdout.split():
        try:
            if os.readlink(f"/proc/{p}/cwd") == BASE:
                open(f"/proc/{p}/oom_score_adj", "w").write("1000")
                res["pid"] = int(p)
        except OSError:
            pass
    time.sleep(0 if a.attach else 10)
    if "Stopping server" in log_text():
        res["error"] = "Server hat sich direkt nach dem Start beendet"
        json.dump(res, open(os.path.join(BASE, "results", a.name + ".json"), "w"), indent=1)
        print(json.dumps(res))
        return
    r = Rcon(rport, pw)
    if not a.attach:
        time.sleep(20)  # Spawn-Chunks fertig laden lassen
    cx, cz = a.center.split()
    answers = []
    for c in (f"chunky world {a.dim}", "chunky shape square", f"chunky center {cx} {cz}", f"chunky radius {a.radius}", "chunky start", "chunky confirm"):
        answers.append(c + " -> " + re.sub(r"§.", "", r.cmd(c)).strip())
    res["chunky_answers"] = answers
    side = 2 * -(-a.radius // 16) + 1
    json.dump({"name": a.name, "label": a.label or a.name, "dim": a.dim, "radius": a.radius,
               "center_chunk": [int(cx) // 16, int(cz) // 16], "side": side, "total": side * side, "started": int(time.time())},
              open(os.path.join(BASE, "results", "_current.json"), "w"))
    time.sleep(5)
    if "No tasks running" in r.cmd("chunky progress"):
        res["error"] = "Chunky hat nicht gestartet"
        json.dump(res, open(os.path.join(BASE, "results", a.name + ".json"), "w"), indent=1)
        print(json.dumps(res, ensure_ascii=False))
        return
    g0 = time.time()
    log_start = len(log_text())
    if a.jfr and res.get("pid"):
        subprocess.run(["sudo", "-u", "minecraft", "/usr/lib/jvm/temurin-17-jdk-amd64/bin/jcmd", str(res["pid"]), "JFR.start",
                        "name=bench", "settings=profile", "duration=420s", f"filename={BASE}/results/{a.name}.jfr"], capture_output=True)
    mspt, last = [], None
    while True:
        time.sleep(15)
        try:
            out = r.cmd(f"forge tps {a.dim}")
            m = re.search(r"Mean tick time: ([\d.,]+) ms", out)
            if m:
                mspt.append(float(m.group(1).replace(",", ".")))
            prog = r.cmd("chunky progress")
        except OSError:
            res["error"] = "Server während der Generierung weg"
            break
        last = prog
        t = log_text()
        if re.search(r"Task finished for " + re.escape(a.dim), t[log_start:]):
            break
        if "No tasks running" in prog and time.time() - g0 > 60:
            # Chunky meldet kurz vor dem Ende schon "No tasks running": auf die Abschlusszeile warten
            for _ in range(12):
                time.sleep(5)
                if re.search(r"Task finished for " + re.escape(a.dim), log_text()[log_start:]):
                    break
            break
        if time.time() - g0 > 7200:
            res["error"] = "Zeitlimit 2 h"
            break
    gen_s = time.time() - g0
    t = log_text()
    m = re.findall(r"Task finished for " + re.escape(a.dim) + r"\. Processed: (\d+) chunks \(([\d.,]+)%\), Total time: ([\d:]+)", t[log_start:])
    chunks = int(m[-1][0]) if m else None
    secs = None
    if m:
        hh, mm, ss = (int(x) for x in m[-1][2].split(":"))
        secs = hh * 3600 + mm * 60 + ss
    res.update(gen_wall_s=round(gen_s), gen_s=secs, chunks=chunks, chunky_time=m[-1][2] if m else None,
               cps=round(chunks / secs, 2) if chunks and secs else None, mspt_mean=round(sum(mspt) / len(mspt), 1) if mspt else None,
               mspt_max=max(mspt) if mspt else None, last_progress=(last or "")[:300],
               exceptions=len(re.findall(r"Exception", t)), errors=len(re.findall(r"/ERROR\]", t)))
    if a.keep:
        json.dump(res, open(os.path.join(BASE, "results", a.name + ".json"), "w"), indent=1)
        print(json.dumps(res))
        return
    try:
        r.cmd("stop")
    except OSError:
        pass
    for _ in range(60):
        time.sleep(3)
        if subprocess.run(["sudo", "-u", "minecraft", "tmux", "has-session", "-t", "cpstest"], stderr=subprocess.DEVNULL).returncode:
            break
    json.dump(res, open(os.path.join(BASE, "results", a.name + ".json"), "w"), indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
