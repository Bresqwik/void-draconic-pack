"""Erzeugt eine verlustfrei verkleinerte the_abyss.json (Datapack-Override) aus der Original-JSON der Mod.
Endpunkte bleiben die Originalzahlen; Nachbarschaft wird mit der Vanilla-Quantisierung geprüft
(Climate.quantizeCoord: (long)(float * 10000f))."""
import json, sys, struct, random
src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding="utf8"))
AX = ["temperature", "humidity", "continentalness", "erosion", "depth", "weirdness"]
f32 = lambda x: struct.unpack("f", struct.pack("f", float(x)))[0]
q = lambda x: int(f32(f32(x) * f32(10000.0)))  # Java: (long)(coord * 10000.0F)
def rng(v):
    return (v[0], v[1]) if isinstance(v, list) else (v, v)
orig = d["generator"]["biome_source"]["biomes"]
entries = [(e["biome"], tuple(rng(e["parameters"][a]) for a in AX), e["parameters"]["offset"]) for e in orig]
def merge_pass(es):
    changed = False
    for ax in range(len(AX)):
        groups = {}
        for b, r, off in es:
            groups.setdefault((b, q(off), tuple((q(r[i][0]), q(r[i][1])) for i in range(len(AX)) if i != ax)), []).append((r, off))
        out = []
        for (b, _, _), rs in groups.items():
            rs.sort(key=lambda x: q(x[0][ax][0]))
            cur, off = list(rs[0][0]), rs[0][1]
            for r, _o in rs[1:]:
                if q(r[ax][0]) <= q(cur[ax][1]):
                    if q(r[ax][1]) > q(cur[ax][1]): cur[ax] = (cur[ax][0], r[ax][1])
                    changed = True
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
def qt(table): return [(b, tuple((q(lo), q(hi)) for lo, hi in r), q(off)) for b, r, off in table]
A, B = qt(entries), qt(es)
def look(t, pt):
    best = bd = None
    for b, r, off in t:
        dd = off * off
        for (lo, hi), x in zip(r, pt):
            if x < lo: dd += (lo - x) ** 2
            elif x > hi: dd += (x - hi) ** 2
        if bd is None or dd < bd: best, bd = b, dd
    return best, bd
random.seed(2); mism = ties = 0; N = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
for _ in range(N):
    pt = [random.randint(-20000, 20000) for _ in AX]; pt[4] = random.choice([0, 0, random.randint(-10000, 10000)])
    a, da = look(A, pt); b, db = look(B, pt)
    if a != b:
        if da == db: ties += 1
        else: mism += 1
print(f"Stichprobe {N}: Abweichungen {mism}, Gleichstand {ties}")
if mism: sys.exit("Abweichungen - nichts geschrieben")
val = lambda lo, hi: lo if lo == hi else [lo, hi]
d["generator"]["biome_source"]["biomes"] = [{"biome": b, "parameters": {**{a: val(*r[i]) for i, a in enumerate(AX)}, "offset": off}} for b, r, off in es]
json.dump(d, open(dst, "w", encoding="utf8"), separators=(",", ":"))
print("geschrieben:", dst)
