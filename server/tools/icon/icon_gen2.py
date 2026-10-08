# Weitere Icon-Alternativen: Drachenkopf vor Eklipse, Drachenei, Flügel mit Kristall.
from icon_gen import *
from PIL import ImageDraw

def to_px(pts):
    return [((x + 1) * S / 2, (y + 1) * S / 2) for x, y in pts]

def catmull(pts, n=10, closed=True):
    P = pts + pts[:3] if closed else pts
    out = []
    for i in range(len(pts) if closed else len(pts) - 3):
        p0, p1, p2, p3 = [np.array(P[i + k]) for k in range(4)]
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(tuple(.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)))
    return out

def poly_mask(pts, smooth=True):
    im = Image.new('L', (S, S), 0)
    ImageDraw.Draw(im).polygon(to_px(catmull(pts) if smooth else pts), fill=255)
    return np.asarray(im, np.float32) / 255

def lines_mask(polys, width):
    im = Image.new('L', (S, S), 0); d = ImageDraw.Draw(im)
    for p in polys: d.line(to_px(p), fill=255, width=width, joint='curve')
    return np.asarray(im, np.float32) / 255

# ---------- C: Drachenkopf vor Eklipse ----------
def eclipse_dragon():
    img = void_bg()
    cx, cy, cr = .3, -.22, .52
    rd = np.hypot(X - cx, Y - cy); ang = np.arctan2(Y - cy, X - cx)
    rays = .7 + .3 * np.sin(ang * 14) * np.sin(ang * 5 + 1)
    img = add(img, col('#ff8a1f'), np.exp(-np.clip(rd - cr, 0, None) * 5) * rays * 1.1)
    img = add(img, col('#ffcf5a'), np.exp(-np.clip(rd - cr, 0, None) * 18) * .8)
    disc = grad(rd / cr, [(0, '#1e0d3a'), (1, '#0a0516')])
    img = over(img, disc, ss(cr, cr - .01, rd))
    img = over(img, col('#ffe28a'), ss(.018, 0, np.abs(rd - cr)))
    head = [(-.75, 1.1), (-.68, .85), (-.9, .78), (-.66, .62), (-.88, .5), (-.6, .4), (-.8, .27), (-.55, .18),
            (-.6, -.02), (-.98, -.5), (-.47, -.18), (-.86, -.8), (-.3, -.33), (-.1, -.3), (0, -.4), (.06, -.27),
            (.45, -.17), (.7, -.12), (.8, -.04), (.74, .04), (.36, .08), (.7, .17), (.63, .23), (.12, .3),
            (-.12, .45), (-.2, 1.1)]
    m = poly_mask(head, smooth=False)
    edge = np.clip(m - blur(m, 4), 0, 1) * 2
    img = add(img, col('#ff9a3a'), blur(m, 10) * (1 - m) * .45)
    body = grad((Y + 1) / 2, [(0, '#1a0b26'), (1, '#07030c')])
    img = over(img, body, m)
    light = ss(1.0, .25, np.hypot(X - cx, Y - cy))
    img = add(img, col('#ffb04a'), edge * light)
    sc = (np.sin(X * 55 + np.sin(Y * 25) * 2) * np.sin(Y * 55)) > .6
    img = add(img, col('#3a1a5c'), sc * m * .3)
    ex, ey = .1, -.2
    e = ((X - ex) / .075) ** 2 + ((Y - ey) / .03) ** 2
    img = add(img, col('#ffcf40'), blur(ss(1.2, .5, e), 6) * 1.3)
    img = over(img, col('#fff2a0'), ss(1, .7, e))
    img = over(img, col('#2a0800'), ss(1, .6, ((X - ex) / .012) ** 2 + ((Y - ey) / .028) ** 2))
    img = add(img, col('#ff6a10'), blur(ss(.03, 0, np.hypot(X - .72, Y + .06)), 5))
    return finish(vignette(img, .4), 'eklipse_drache')

# ---------- D: Drachenei mit glühenden Rissen ----------
def dragon_egg():
    img = void_bg()
    Yc = Y - .06
    a = .56 * (1 + .2 * Yc)
    e = (X / a) ** 2 + (Yc / .78) ** 2
    m = ss(1.02, .98, e)
    img = add(img, col('#ff7a1a'), blur(ss(1.6, .9, e) * (Y > 0), 30) * .6)
    img = add(img, col('#a34cff'), blur(ss(1.25, 1, e), 16) * .8)
    # Schattierung wie Kugel
    nz = np.sqrt(np.clip(1 - e, 0, 1))
    nx, ny = X / a * (1 - nz * .2), Yc / .78
    lam = np.clip(-.45 * nx - .55 * ny + .7 * nz, 0, 1)
    base = grad(lam, [(0, '#070310'), (.5, '#26103f'), (.85, '#5a2a8c'), (1, '#9b6ad6')])
    speck = blur(rng.random((S, S)).astype(np.float32), 3)
    base = add(base, col('#c08bff'), ss(.62, .72, speck) * .35)
    img = over(img, base, m)
    # Risse
    polys = []
    def crack(x, y, ang, n, depth):
        pts = [(x, y)]
        for _ in range(n):
            ang += rng.normal(0, .5); x += np.cos(ang) * .07; y += np.sin(ang) * .07; pts.append((x, y))
            if depth < 2 and rng.random() < .25:
                crack(x, y, ang + rng.choice([-1, 1]) * rng.uniform(.6, 1.1), n // 2, depth + 1)
        polys.append(pts)
    main = [(-.42, -.02), (-.28, .07), (-.15, -.05), (-.02, .07), (.12, -.04), (.26, .06), (.42, -.03)]
    polys += [main, [(-.15, -.05), (-.2, -.22), (-.13, -.33)], [(.12, -.04), (.18, -.2), (.1, -.36), (.16, -.48)],
              [(-.02, .07), (.04, .24), (-.04, .38)], [(.26, .06), (.3, .22)], [(-.28, .07), (-.32, .24), (-.24, .36)]]
    cm = lines_mask(polys, 7) * m
    img = add(img, col('#ff7a1a'), blur(cm, 10) * m * 1.4)
    img = over(img, col('#ffe08a'), cm)
    img = over(img, col('#fffbe0'), lines_mask(polys, 2) * m)
    # Glanz
    img = add(img, col('#ffffff'), ss(.14, 0, np.hypot((X + .2) / 1.2, Yc + .42)) * m * .45)
    return finish(vignette(img, .45), 'drachenei')

# ---------- E: Drachenflügel mit Draconic-Kristall ----------
def wings_crystal():
    img = void_bg()
    img = add(img, col('#ff7a1a'), ss(.6, 0, R) * .25)
    wing = [(.06, -.02), (.25, -.42), (.55, -.62), (.95, -.78), (.82, -.5), (.92, -.2), (.74, -.12),
            (.86, .14), (.62, .06), (.66, .36), (.44, .2), (.36, .44), (.2, .22), (.08, .2)]
    left = [(-x, y) for x, y in wing]
    m = np.maximum(poly_mask(wing), poly_mask(left))
    img = add(img, col('#b44cff'), blur(m, 12) * (1 - m) * .9)
    memb = grad(np.abs(X), [(0, '#5a2a8c'), (.5, '#33175a'), (1, '#160a2a')])
    img = over(img, memb, m)
    # Flügelknochen
    bones = []
    for sgn in (1, -1):
        bones += [[(sgn * .1, -.0), (sgn * .3, -.42), (sgn * .6, -.62), (sgn * .95, -.78)],
                  [(sgn * .3, -.42), (sgn * .92, -.2)], [(sgn * .3, -.42), (sgn * .86, .14)],
                  [(sgn * .3, -.42), (sgn * .66, .36)], [(sgn * .3, -.42), (sgn * .36, .44)]]
    bm = lines_mask(bones, 9) * m
    img = over(img, col('#12081f'), bm)
    img = add(img, col('#d58cff'), lines_mask(bones, 3) * m * .5)
    img = add(img, col('#ffffff'), np.clip(m - blur(m, 3), 0, 1) * 1.4 * .5)
    # Kristall (Raute)
    k = np.abs(X) / .2 + np.abs(Y - .02) / .36
    km = ss(1.03, .97, k)
    img = add(img, col('#ff8a1a'), blur(km, 18) * 1.2)
    side = np.where(X < 0, 1.0, .7) * np.where(Y < .02, 1.0, .8)
    cry = grad(k, [(0, '#fff3b8'), (.5, '#ffb52e'), (1, '#e0520c')]) * side[..., None]
    img = over(img, cry, km)
    img = over(img, col('#fff4c4'), lines_mask([[(0, -.34), (0, .38)], [(-.2, .02), (.2, .02)]], 3) * km * .6)
    img = over(img, col('#ffffff'), ss(.06, .01, np.hypot(X + .05, Y + .1)) * .9)
    return finish(vignette(img, .4), 'fluegel_kristall')

if __name__ == '__main__':
    eclipse_dragon(); dragon_egg(); wings_crystal()
