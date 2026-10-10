#!/usr/bin/env python3
"""RCON an die CPS-Testbank: vd-rcon "befehl" ["befehl" ...]"""
import re, socket, struct, sys
p = dict(l.split("=", 1) for l in open("/opt/vd-cps-test/server.properties").read().splitlines() if "=" in l and not l.startswith("#"))
s = socket.create_connection(("127.0.0.1", int(p["rcon.port"])), timeout=60)
def rd(n):
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c: raise OSError("closed")
        d += c
    return d
def send(i, t, b):
    b = b.encode(); s.sendall(struct.pack("<iii", len(b) + 10, i, t) + b + b"\0\0")
    n = struct.unpack("<i", rd(4))[0]; return rd(n)[8:-2].decode("utf-8", "replace")
send(1, 3, p["rcon.password"])
for c in sys.argv[1:]:
    print(">", c); print(re.sub(r"§.", "", send(2, 2, c)))
