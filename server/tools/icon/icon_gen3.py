# Varianten in Richtung B (Void-Wirbel + Kern) und E (Flügel + Kristall), baukastenartig.
from icon_gen2 import *

def vortex(img, arms=3, twist=7.5, c1='#9b45ff', c2='#ff5ad1', strength=1.0, ring=True, r_out=1.05):
    sw = np.sin(A * arms + np.log(R + .03) * twist)
    a = ss(.2, 1, sw) * ss(.05, .25, R) * (1 - ss(r_out - .3, r_out, R))
    img = add(img, col(c1), blur(a, 3) * .75 * strength)
    img = add(img, col(c2), blur(ss(.75, 1, sw) * ss(.12, .3, R) * (1 - ss(r_out - .5, r_out - .15, R)), 2) * .45 * strength)
    if ring:
        img = add(img, col('#c58bff'), blur(ss(.03, 0, np.abs(R - .78)), 4) * .8 * strength)
    return img

def dark_center(img, r=.42, glow='#ff7a1a', g=.9):
    img = over(img, col('#000000'), ss(r, r * .45, R) * .85)
    return add(img, col(glow), blur(ss(r, r * .35, R), 18) * g)

def hex_core(img, size=.34, stops=None):
    stops = stops or [(0, '#fff7c9'), (.35, '#ffc43a'), (.75, '#ff7414'), (1, '#b02e05')]
    hexd = np.maximum.reduce([np.abs(X * np.cos(k * np.pi / 3) + Y * np.sin(k * np.pi / 3)) for k in range(3)])
    hm = ss(size + .005, size - .005, hexd)
    shade = .5 + .5 * np.cos(A * 3 + 1.2)
    core = grad(R / size, stops) * (.75 + .35 * shade[..., None])
    img = over(img, core, hm)
    img = over(img, col(stops[0][1]), ss(.012, 0, np.abs(hexd - size)) * .9)
    for k in range(6):
        a0 = k * np.pi / 3 + np.pi / 6
        d = np.abs(-np.sin(a0) * X + np.cos(a0) * Y); al = np.cos(a0) * X + np.sin(a0) * Y
        img = over(img, col(stops[0][1]), ss(.007, 0, d) * (al > 0) * hm * .5)
    return over(img, col('#ffffff'), ss(.07, .02, R) * .9)

def diamond(img, w=.2, h=.36, cy=.02, stops=None, glow='#ff8a1a'):
    stops = stops or [(0, '#fff3b8'), (.5, '#ffb52e'), (1, '#e0520c')]
    k = np.abs(X) / w + np.abs(Y - cy) / h
    km = ss(1.03, .97, k)
    img = add(img, col(glow), blur(km, 18) * 1.2)
    side = np.where(X < 0, 1.0, .7) * np.where(Y < cy, 1.0, .8)
    img = over(img, grad(k, stops) * side[..., None], km)
    img = over(img, col(stops[0][1]), lines_mask([[(0, cy - h), (0, cy + h)], [(-w, cy), (w, cy)]], 3) * km * .6)
    return over(img, col('#ffffff'), ss(.06, .01, np.hypot(X + w * .25, Y - cy + h * .3)) * .9)

def orb(img, r=.26, stops=None, ring_col='#ffd36b'):
    stops = stops or [(0, '#fffbe6'), (.3, '#ffd04a'), (.7, '#ff7a14'), (1, '#9a2604')]
    img = add(img, col('#ff7a1a'), blur(ss(r * 1.6, r * .6, R), 16) * 1.1)
    m = ss(r + .005, r - .005, R)
    swirl = .85 + .15 * np.sin(A * 5 + R * 30)
    img = over(img, grad(R / r, stops) * swirl[..., None], m)
    # zwei schräge Orbitringe
    for rot in (.5, -.5):
        xr = X * np.cos(rot) - Y * np.sin(rot); yr = X * np.sin(rot) + Y * np.cos(rot)
        e = np.hypot(xr / (r * 1.75), yr / (r * .55))
        band = ss(.06, 0, np.abs(e - 1))
        front = (yr > 0) | (R > r)
        img = over(img, col(ring_col), band * front * .95)
    return over(img, col('#ffffff'), ss(.06, .015, np.hypot(X + .07, Y + .08)) * .9)

WING = [(.06, -.02), (.25, -.42), (.55, -.62), (.95, -.78), (.82, -.5), (.92, -.2), (.74, -.12),
        (.86, .14), (.62, .06), (.66, .36), (.44, .2), (.36, .44), (.2, .22), (.08, .2)]

def wings(img, scale=1.0, dy=0.0, memb=None, bone='#12081f', glow='#b44cff', edge=.7, alpha=1.0):
    memb = memb or [(0, '#5a2a8c'), (.5, '#33175a'), (1, '#160a2a')]
    w = [(x * scale, y * scale + dy) for x, y in WING]
    m = np.maximum(poly_mask(w), poly_mask([(-x, y) for x, y in w])) * alpha
    img = add(img, col(glow), blur(m, 12) * (1 - m) * .9)
    img = over(img, grad(np.abs(X) / scale, memb), m)
    bones = []
    for s in (1, -1):
        P = lambda x, y: (s * x * scale, y * scale + dy)
        bones += [[P(.1, 0), P(.3, -.42), P(.6, -.62), P(.95, -.78)], [P(.3, -.42), P(.92, -.2)],
                  [P(.3, -.42), P(.86, .14)], [P(.3, -.42), P(.66, .36)], [P(.3, -.42), P(.36, .44)]]
    img = over(img, col(bone), lines_mask(bones, max(4, int(9 * scale))) * m)
    img = add(img, col('#d58cff'), lines_mask(bones, 3) * m * .5)
    return add(img, col('#ffffff'), np.clip(m - blur(m, 3), 0, 1) * edge)

ORANGE_MEMB = [(0, '#c2551a'), (.5, '#7a2a0e'), (1, '#2a0c05')]
VOID_STOPS = [(0, '#f3e6ff'), (.4, '#c48bff'), (.8, '#7a2fd6'), (1, '#3a0f78')]

def v1():  # B + E: Wirbel, Flügel, Hex-Kern
    img = vortex(void_bg(), strength=.85)
    img = wings(img, scale=.98, alpha=.92)
    img = dark_center(img, r=.36, g=.7)
    return finish(vignette(hex_core(img, size=.27), .4), 'v1_wirbel_fluegel')

def v2():  # Wirbel mit Draconic-Energiekern (Orb + Ringe)
    img = vortex(void_bg(), arms=4, twist=6.5)
    img = dark_center(img, r=.4)
    return finish(vignette(orb(img, r=.24), .4), 'v2_wirbel_orb')

def v3():  # Wirbel enger, Rauten-Kristall
    img = vortex(void_bg(), arms=2, twist=9, c2='#ff8fe0')
    img = dark_center(img, r=.4)
    return finish(vignette(diamond(img, w=.19, h=.34), .4), 'v3_wirbel_raute')

def v4():  # Flügel orange (Draconic), Void-Kristall violett
    img = void_bg()
    img = add(img, col('#b44cff'), ss(.6, 0, R) * .25)
    img = wings(img, memb=ORANGE_MEMB, bone='#1c0904', glow='#ff7a1a')
    return finish(vignette(diamond(img, stops=VOID_STOPS, glow='#a64cff'), .4), 'v4_fluegel_orange')

def v5():  # Flügel + Kristall vor Portalring
    img = void_bg()
    img = add(img, col('#c58bff'), blur(ss(.035, 0, np.abs(R - .7)), 5) * 1.0)
    img = add(img, col('#ff7a1a'), blur(ss(.02, 0, np.abs(R - .7)), 2) * .6)
    img = wings(img, scale=.92, dy=.02)
    return finish(vignette(diamond(img), .4), 'v5_fluegel_ring')

def v6():  # Wirbel violett/blau mit violettem Hex-Kern und orangem Ring (Farben getauscht)
    img = vortex(void_bg(), c1='#ff7a1a', c2='#ffd36b', strength=.8)
    img = dark_center(img, r=.42, glow='#a64cff')
    return finish(vignette(hex_core(img, size=.33, stops=VOID_STOPS), .4), 'v6_wirbel_invers')

if __name__ == '__main__':
    for f in (v1, v2, v3, v4, v5, v6): f()
