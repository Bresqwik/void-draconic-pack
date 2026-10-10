"""Wie abyss_compact.py, aber ohne Fremdbibliotheken (läuft mit dem System-Python des Servers).
Eigener NBT-Leser/-Schreiber, der Tag-Typen und Reihenfolge exakt erhält.
Aufruf: python3 abyss_compact_raw.py <level.dat> [--write] [--roundtrip-test]"""
import sys, gzip, struct, io, shutil

def rd(b):
    def rs():
        n = struct.unpack(">H", b.read(2))[0]; return b.read(n).decode("utf8")
    def val(t):
        if t == 1: return b.read(1)
        if t == 2: return b.read(2)
        if t == 3: return b.read(4)
        if t == 4: return b.read(8)
        if t == 5: return b.read(4)
        if t == 6: return b.read(8)
        if t == 7: n = b.read(4); return n + b.read(struct.unpack(">i", n)[0])
        if t == 8: return rs()
        if t == 9:
            et = b.read(1)[0]; n = struct.unpack(">i", b.read(4))[0]
            return (et, [val(et) for _ in range(n)])
        if t == 10:
            o = []
            while True:
                tt = b.read(1)[0]
                if tt == 0: return o
                k = rs(); o.append([k, tt, val(tt)])
        if t == 11: n = b.read(4); return n + b.read(4 * struct.unpack(">i", n)[0])
        if t == 12: n = b.read(4); return n + b.read(8 * struct.unpack(">i", n)[0])
        raise ValueError(t)
    t = b.read(1)[0]; name = rs(); return (t, name, val(t))

def wr(root):
    o = io.BytesIO()
    def ws(s):
        e = s.encode("utf8"); o.write(struct.pack(">H", len(e))); o.write(e)
    def val(t, v):
        if t in (1, 2, 3, 4, 5, 6, 7, 11, 12): o.write(v)
        elif t == 8: ws(v)
        elif t == 9:
            et, items = v; o.write(bytes([et if items else et])); o.write(struct.pack(">i", len(items)))
            for x in items: val(et, x)
        elif t == 10:
            for k, tt, x in v:
                o.write(bytes([tt])); ws(k); val(tt, x)
            o.write(b"\0")
    t, name, v = root; o.write(bytes([t])); ws(name); val(t, v)
    return o.getvalue()

def get(comp, key):
    for e in comp:
        if e[0] == key: return e
    raise KeyError(key)

path = sys.argv[1]
raw = gzip.open(path).read()
root = rd(io.BytesIO(raw))
if "--roundtrip-test" in sys.argv:
    print("Roundtrip identisch:", wr(root) == raw)

AX = ["temperature", "humidity", "continentalness", "erosion", "depth", "weirdness"]
fl = lambda by: struct.unpack(">f", by)[0]
Q = lambda f: int(round(f * 10000))
c = root[2]
for k in ["Data", "WorldGenSettings", "dimensions", "theabyss:the_abyss", "generator", "biome_source"]:
    c = get(c, k)[2]
biomes_e = get(c, "biomes")
et, items = biomes_e[2]
entries = []
for comp in items:
    b = get(comp, "biome")[2]; p = get(comp, "parameters")[2]
    r = []
    for a in AX:
        _, tt, v = get(p, a)
        r.append((Q(fl(v[1][0])), Q(fl(v[1][1]))) if tt == 9 else (Q(fl(v)), Q(fl(v))))
    entries.append((b, tuple(r), Q(fl(get(p, "offset")[2]))))

def merge_pass(es):
    changed = False
    for ax in range(len(AX)):
        groups = {}
        for b, r, off in es:
            groups.setdefault((b, off, tuple(r[i] for i in range(len(AX)) if i != ax)), []).append(r)
        out = []
        for (b, off, _), rs in groups.items():
            rs.sort(key=lambda r: r[ax]); cur = list(rs[0])
            for r in rs[1:]:
                if r[ax][0] <= cur[ax][1]:
                    cur[ax] = (cur[ax][0], max(cur[ax][1], r[ax][1])); changed = True
                else:
                    out.append((b, tuple(cur), off)); cur = list(r)
            out.append((b, tuple(cur), off))
        es = out
    return es, changed
es = entries
while True:
    es, ch = merge_pass(es)
    if not ch: break
print(f"Einträge: {len(entries)} -> {len(es)}")
if len(entries) < 3000:
    sys.exit("Tabelle schon kompakt - nichts zu tun")

F = lambda q: struct.pack(">f", q / 10000)
new = []
for b, r, off in es:
    p = []
    for i, a in enumerate(AX):
        lo, hi = r[i]
        p.append([a, 5, F(lo)] if lo == hi else [a, 9, (5, [F(lo), F(hi)])])
    p.append(["offset", 5, F(off)])
    new.append([["biome", 8, b], ["parameters", 10, p]])
biomes_e[2] = (10, new)
out = wr(root)
print(f"unkomprimiert: {len(raw)} -> {len(out)}")
if "--write" in sys.argv:
    shutil.copy2(path, path + ".vor-abyss-compact")
    with gzip.open(path + ".neu", "wb") as g: g.write(out)
    rd(io.BytesIO(gzip.open(path + ".neu").read()))  # Lesetest
    shutil.move(path + ".neu", path)
    print("geschrieben, Sicherung:", path + ".vor-abyss-compact")
