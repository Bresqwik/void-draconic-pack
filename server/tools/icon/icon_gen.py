# Erzeugt hochwertige 64x64-Servericons (supersampled 512 -> 64, Lanczos + leichtes Schärfen).
import numpy as np, sys, os
from PIL import Image, ImageFilter

S = 512
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
X = (xx + .5) / S * 2 - 1
Y = (yy + .5) / S * 2 - 1
R = np.hypot(X, Y)
A = np.arctan2(Y, X)
rng = np.random.default_rng(7)

def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

def col(h):
    h = h.lstrip('#'); return np.array([int(h[i:i+2], 16) / 255 for i in (0, 2, 4)], np.float32)

def grad(t, stops):
    t = np.clip(t, 0, 1); out = np.zeros(t.shape + (3,), np.float32)
    pos = [p for p, _ in stops]; cs = [col(c) for _, c in stops]
    for c in range(3):
        out[..., c] = np.interp(t, pos, [k[c] for k in cs])
    return out

def over(img, color, alpha):
    a = np.clip(alpha, 0, 1)[..., None]
    if np.ndim(color) == 1: color = np.broadcast_to(color, img.shape)
    return img * (1 - a) + color * a

def add(img, color, amount):
    if np.ndim(color) == 1: color = np.broadcast_to(color, img.shape)
    return img + color * np.clip(amount, 0, None)[..., None]

def blur(m, r):
    im = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255

def void_bg():
    img = grad(R / 1.45, [(0, '#2a1250'), (.45, '#160a2e'), (1, '#05030c')])
    # Nebel
    n = blur(rng.random((S, S)).astype(np.float32), 40)
    n = (n - n.min()) / (n.max() - n.min())
    img = add(img, col('#6b2fb8'), ss(.55, 1, n) * .35 * (1 - ss(.3, 1.3, R)))
    # Sterne
    stars = np.zeros((S, S), np.float32)
    for _ in range(70):
        x, y = rng.integers(0, S, 2); r = rng.uniform(1.5, 4.5)
        stars = np.maximum(stars, ss(r, r * .3, np.hypot(xx - x, yy - y)) * rng.uniform(.4, 1))
    img = add(img, col('#e8dcff'), stars)
    return img

def vignette(img, k=.55):
    return img * (1 - k * ss(.85, 1.5, R))[..., None]

def finish(img, name):
    img = np.clip(img, 0, 1)
    big = Image.fromarray((img * 255).astype(np.uint8), 'RGB')
    small = big.resize((64, 64), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=1))
    small.save(os.path.join(OUT, name + '.png'), optimize=True)
    big.save(os.path.join(OUT, name + '_512.png'))
    return small

# ---------- A: Drachenauge mit Void-Pupille ----------
def dragon_eye():
    global X, Y, R, A
    img = void_bg()
    X0, Y0 = X, Y
    X, Y = X0 / 1.16, Y0 / 1.16; R = np.hypot(X, Y); A = np.arctan2(Y, X)
    # Mandelform: Schnitt zweier Kreise
    d, rr = .5, .92
    e1 = np.hypot(X, Y - d) - rr; e2 = np.hypot(X, Y + d) - rr
    eye_sd = np.maximum(e1, e2)                       # <0 innen
    aura = blur((eye_sd < .06).astype(np.float32), 22)
    img = add(img, col('#b44cff'), aura * .9)
    img = add(img, col('#ff7a1a'), blur((eye_sd < 0).astype(np.float32), 10) * .35)
    # dunkler Lidrand + Schuppen-Kante
    rim = ss(.035, .0, np.abs(eye_sd + .02))
    img = over(img, col('#0c0614'), ss(.0, -.01, eye_sd - .05) )
    inside = ss(.006, -.006, eye_sd)
    # Lederhaut: dunkles Rot-Violett
    sclera = grad((Y + .4) / .8, [(0, '#3a0f1e'), (1, '#1a0712')])
    img = over(img, sclera, inside)
    # Iris
    ir = .43
    fib = np.sin(A * 46 + np.sin(A * 7) * 2) * .5 + .5
    fib2 = blur(rng.random((S, S)).astype(np.float32), 2.5)
    t = R / ir
    iris = grad(t, [(0, '#fff6b0'), (.22, '#ffd23a'), (.55, '#ff8a12'), (.82, '#d6400c'), (1, '#5a1206')])
    iris = iris * (0.82 + .25 * fib[..., None] * ss(.15, .6, t)[..., None] + .12 * (fib2[..., None] - .5))
    im = ss(ir + .006, ir - .006, R) * inside
    img = over(img, iris, im)
    img = over(img, col('#2a0804'), ss(.012, 0, np.abs(R - ir)) * inside * .9)  # Irisring
    # Pupille: senkrechter Schlitz, darin Void
    psd = (X / .062) ** 2 + (Y / .39) ** 2
    pm = ss(1.08, .92, psd) * inside
    pgl = blur(pm, 9)
    img = over(img, col('#2a0a00'), pgl * .7 * im)
    void_in = grad(np.abs(Y) / .4, [(0, '#3d1680'), (.6, '#12052a'), (1, '#05020c')])
    img = over(img, void_in, pm)
    sp = np.zeros((S, S), np.float32)
    for (sx, sy, r) in [(-.01, -.16, 3.2), (.02, .05, 2.4), (-.02, .2, 2.8), (.015, -.28, 2)]:
        px, py = (sx + 1) * S / 2, (sy + 1) * S / 2
        sp = np.maximum(sp, ss(r, r * .2, np.hypot(xx - px, yy - py)))
    img = add(img, col('#e3d0ff'), sp * pm)
    # Glanzlicht
    hl = ss(.075, .03, np.hypot(X + .17, Y + .17)) * inside
    img = over(img, col('#ffffff'), hl * .95)
    img = over(img, col('#ffffff'), ss(.035, .01, np.hypot(X - .2, Y - .2)) * inside * .6)
    # Lid-Schatten oben
    img = img * (1 - .45 * inside * ss(-.15, -.55, Y) * ss(-.3, 0, eye_sd + .0))[..., None]
    img = over(img, col('#9d5cff'), rim * .85)
    X, Y = X0, Y0; R = np.hypot(X, Y); A = np.arctan2(Y, X)
    return finish(vignette(img), 'drachenauge')

# ---------- B: Void-Wirbel mit Draconic-Kern ----------
def vortex_core():
    img = void_bg()
    sw = np.sin(A * 3 + np.log(R + .03) * 7.5)
    arms = ss(.2, 1, sw) * ss(.05, .25, R) * (1 - ss(.75, 1.05, R))
    img = add(img, col('#9b45ff'), blur(arms, 3) * .75)
    img = add(img, col('#ff5ad1'), blur(ss(.75, 1, sw) * ss(.12, .3, R) * (1 - ss(.55, .9, R)), 2) * .45)
    ring = ss(.03, 0, np.abs(R - .78))
    img = add(img, col('#c58bff'), blur(ring, 4) * .8)
    img = over(img, col('#000000'), ss(.42, .2, R) * .85)   # dunkles Zentrum
    img = add(img, col('#ff7a1a'), blur(ss(.42, .15, R), 18) * .9)
    # Sechseck-Kristall
    hexd = np.maximum.reduce([np.abs(X * np.cos(k * np.pi / 3) + Y * np.sin(k * np.pi / 3)) for k in range(3)])
    hm = ss(.345, .335, hexd)
    shade = .5 + .5 * np.cos(A * 3 + 1.2)  # facettiert
    core = grad(R / .34, [(0, '#fff7c9'), (.35, '#ffc43a'), (.75, '#ff7414'), (1, '#b02e05')])
    core = core * (.75 + .35 * shade[..., None])
    img = over(img, core, hm)
    img = over(img, col('#ffe9a8'), ss(.012, 0, np.abs(hexd - .34)) * .9)
    # Facettenlinien
    for k in range(6):
        a0 = k * np.pi / 3 + np.pi / 6
        dist = np.abs(-np.sin(a0) * X + np.cos(a0) * Y)
        along = np.cos(a0) * X + np.sin(a0) * Y
        img = over(img, col('#ffe7a0'), ss(.007, 0, dist) * (along > 0) * hm * .55)
    img = over(img, col('#ffffff'), ss(.07, .02, np.hypot(X, Y)) * .9)
    return finish(vignette(img), 'void_kern')

if __name__ == "__main__":
    dragon_eye(); vortex_core()
