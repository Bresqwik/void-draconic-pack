#!/usr/bin/env python3
"""Wertet eine JFR-Aufnahme aus: wo verbringen die Threads ihre Zeit? Aufruf: jfr_top.py <datei.jfr>
Zählt Samples je Thread-Gruppe, je oberster Methode und je "verantwortlichem" Paket (erster Frame außerhalb von
java./jdk./sun./net.minecraft.)."""
import collections, re, subprocess, sys

JFR = "/usr/lib/jvm/temurin-17-jdk-amd64/bin/jfr"
out = subprocess.run([JFR, "print", "--events", "jdk.ExecutionSample", "--stack-depth", "40", sys.argv[1]],
                     capture_output=True, text=True).stdout
threads, top, owner, mcmeth = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
n = 0
for ev in out.split("jdk.ExecutionSample {")[1:]:
    m = re.search(r'sampledThread = "([^"]+)"', ev)
    th = re.sub(r"[-#]?\d+$", "", m.group(1)) if m else "?"
    frames = re.findall(r"^\s+([\w$.<>/]+)\(", ev, re.M)
    if not frames:
        continue
    n += 1
    threads[th] += 1
    top[frames[0]] += 1
    own = next((f for f in frames if not re.match(r"(java|jdk|sun|net\.minecraft|com\.mojang|it\.unimi|com\.google)\.", f)), None)
    owner[".".join(own.split(".")[:3]) if own else "vanilla/jdk"] += 1
    mc = next((f for f in frames if f.startswith("net.minecraft.")), None)
    if mc:
        mcmeth[mc] += 1
print(f"{n} Samples")
for title, c, k in (("Threads", threads, 12), ("Pakete (erster Nicht-Vanilla-Frame)", owner, 25), ("Oberste Methode", top, 25), ("Erste Minecraft-Methode", mcmeth, 25)):
    print(f"\n== {title}")
    for name, v in c.most_common(k):
        print(f"{v * 100 / max(n, 1):5.1f}%  {name}")
