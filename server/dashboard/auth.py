#!/usr/bin/env python3
"""Void & Draconic Dashboard – Anmeldung (Dienst mc-dashboard-auth, nur auf 127.0.0.1:8790).

Ersetzt das graue Basic-Auth-Fenster des Browsers durch eine eigene Login-Seite. Caddy fragt per forward_auth
bei /auth/check nach, ob die Sitzung gültig ist. Benutzer und Passwort-Hash (bcrypt) kommen weiter aus
/etc/caddy/dashboard.env, gesetzt mit "dashboard-passwort". Ändert sich das Passwort, werden alle Sitzungen ungültig.

  GET  /auth/login    Login-Seite (der Browser kann die Zugangsdaten speichern)
  POST /auth/login    prüft die Daten, setzt das Sitzungs-Cookie ("Angemeldet bleiben": 30 Tage, sonst bis zum Schließen)
  GET  /auth/check    200 bei gültiger Sitzung, sonst 401 (Daten) oder Weiterleitung zur Login-Seite
  GET  /auth/logout   meldet ab
  POST /api/pregen/watch  {"watch": true|false}  Pregen pausieren, wenn Spieler online sind (Schalter im Dashboard)
  POST /api/pregen/plan   {"radii": {...}, "shape": "square"}  Plan aus dem Pregen-Rechner (wird erst nach Absprache eingeplant)
Die API schreibt nur nach /var/lib/mc-dashboard/control, der Datensammler liest dort.
"""
import base64, hashlib, hmac, html, json, os, secrets, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bcrypt

ENV = "/etc/caddy/dashboard.env"
SECRET_FILE = os.path.join(os.environ.get("STATE_DIRECTORY", "/var/lib/mc-dashboard-auth"), "secret")
COOKIE = "vd_session"
REMEMBER = 30 * 86400      # "Angemeldet bleiben"
SESSION = 12 * 3600        # ohne Haken: Browser-Sitzung, spätestens nach 12 Stunden neu anmelden
FAILS, LOCK_AFTER, LOCK_FOR = {}, 5, 300
CONTROL = "/var/lib/mc-dashboard/control"
DIMS = {"ow", "ne", "end", "ae", "tf", "os"}


def creds():
    d = {}
    try:
        for line in open(ENV, encoding="utf-8"):
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                d[k] = v
    except OSError:
        pass
    return d.get("DASH_USER", ""), d.get("DASH_HASH", "")


def secret():
    try:
        return open(SECRET_FILE, "rb").read()
    except OSError:
        os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
        s = secrets.token_bytes(32)
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, s)
        os.close(fd)
        return s


def key():
    # Der Passwort-Hash gehört zum Schlüssel: neues Passwort = alle alten Sitzungen ungültig
    return hashlib.sha256(secret() + creds()[1].encode()).digest()


def sign(user, exp):
    body = base64.urlsafe_b64encode(f"{user}|{exp}".encode()).decode().rstrip("=")
    mac = hmac.new(key(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def valid(cookie_header):
    for part in (cookie_header or "").split(";"):
        name, _, val = part.strip().partition("=")
        if name != COOKIE or "." not in val:
            continue
        body, mac = val.rsplit(".", 1)
        if not hmac.compare_digest(mac, hmac.new(key(), body.encode(), hashlib.sha256).hexdigest()):
            continue
        try:
            user, exp = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode().split("|")
        except ValueError:
            continue
        if user == creds()[0] and int(exp) > time.time():
            return True
    return False


def safe_next(n):
    n = n or "/"
    return n if n.startswith("/") and not n.startswith("//") and not n.startswith("/auth/") else "/"


PAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#06040d">
<title>Anmelden · Void &amp; Draconic Server-Konsole</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%23140a26'/%3E%3Cpath d='M8 2l4 4-4 8-4-8z' fill='%239d6cff'/%3E%3Cpath d='M8 2l4 4-4 8z' fill='%23ff7a3d'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@600;800&family=Rethink+Sans:wght@400;500;600;700&family=Martian+Mono:wght@400;600&display=swap">
<style>
/* Gleiche Welt wie die Server-Konsole: Void-Hintergrund, schwebender Kristall, eine Glas-Karte. */
:root{
  color-scheme:dark;
  --void:#06040d; --panel:rgba(22,14,44,.78); --line:rgba(185,140,255,.2); --line-strong:rgba(185,140,255,.5);
  --ink:#eeeaf8; --muted:#a69dc2; --violet:#9d6cff; --violet-soft:#c4a6ff; --ember:#ff7a3d; --cyan:#45dbe9; --red:#ff5d66; --green:#5fd672;
  --display:"Unbounded","Arial Black",system-ui,sans-serif;
  --body:"Rethink Sans","Segoe UI",system-ui,sans-serif;
  --mono:"Martian Mono",Consolas,ui-monospace,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--void);color:var(--ink);font:15px/1.5 var(--body);display:grid;place-items:center;padding:24px 16px;overflow:hidden}
body::before{content:"";position:fixed;inset:-20%;pointer-events:none;animation:drift 50s ease-in-out infinite alternate;
  background:radial-gradient(40% 35% at 20% 25%,rgba(157,108,255,.26),transparent 70%),
             radial-gradient(35% 30% at 85% 15%,rgba(255,122,61,.16),transparent 70%),
             radial-gradient(45% 40% at 60% 95%,rgba(69,219,233,.08),transparent 70%)}
@keyframes drift{to{transform:translate3d(3%,-2%,0) scale(1.06)}}
#sky{position:fixed;inset:0;width:100%;height:100%;pointer-events:none}
main{position:relative;width:100%;max-width:400px;display:grid;gap:22px;justify-items:center}
.crystal{width:84px;height:84px;filter:drop-shadow(0 0 22px rgba(157,108,255,.7)) drop-shadow(0 0 40px rgba(255,122,61,.25));animation:float 6s ease-in-out infinite}
@keyframes float{50%{transform:translateY(-8px)}}
.title{text-align:center;display:grid;gap:6px}
h1{font:800 22px/1.15 var(--display);margin:0;letter-spacing:-.01em}
.title small{font:600 10.5px/1 var(--mono);letter-spacing:.2em;color:var(--muted)}
form{width:100%;background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:24px 22px;display:grid;gap:16px;
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:0 30px 80px rgba(0,0,0,.45)}
label.f{display:grid;gap:7px;font:600 10.5px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
input[type=text],input[type=password]{width:100%;font:500 16px var(--body);color:var(--ink);background:rgba(6,4,13,.6);border:1px solid var(--line);
  border-radius:12px;padding:12px 14px;transition:border-color .2s,box-shadow .2s;letter-spacing:normal;text-transform:none}
input[type=text]:focus,input[type=password]:focus{outline:none;border-color:var(--violet);box-shadow:0 0 0 3px rgba(157,108,255,.25)}
.pw{position:relative}
.pw input{padding-right:52px}
.eye{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:0;color:var(--muted);cursor:pointer;padding:8px;border-radius:8px;font:600 12px var(--mono)}
.eye:hover{color:var(--ink)}
.remember{display:flex;align-items:center;gap:10px;font-size:14px;color:var(--ink);cursor:pointer;user-select:none}
.remember input{width:18px;height:18px;accent-color:var(--violet);margin:0}
.remember span small{display:block;color:var(--muted);font-size:12.5px}
button.go{font:800 14px/1 var(--display);letter-spacing:.02em;color:#fff;border:0;border-radius:12px;padding:15px;cursor:pointer;
  background:linear-gradient(100deg,var(--violet),#b45cf0 55%,var(--ember));box-shadow:0 10px 30px rgba(157,108,255,.35);transition:transform .15s,filter .2s}
button.go:hover{filter:brightness(1.1)}
button.go:active{transform:translateY(1px)}
button.go[disabled]{filter:grayscale(.5) brightness(.8);cursor:wait}
:focus-visible{outline:2px solid var(--cyan);outline-offset:3px}
.msg{font-size:14px;border-radius:10px;padding:10px 12px;border:1px solid}
.msg.err{color:var(--red);border-color:rgba(255,93,102,.4);background:rgba(255,93,102,.08)}
.msg.ok{color:var(--green);border-color:rgba(95,214,114,.4);background:rgba(95,214,114,.08)}
.foot{font:500 11px/1.5 var(--mono);color:var(--muted);text-align:center;letter-spacing:.04em}
.foot b{color:var(--violet-soft);font-weight:600}
@media (prefers-reduced-motion: reduce){body::before,.crystal{animation:none}}
</style>
</head>
<body>
<canvas id="sky" aria-hidden="true"></canvas>
<main>
  <svg class="crystal" viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#c4a6ff"/><stop offset="1" stop-color="#ff7a3d"/></linearGradient></defs>
    <path d="M16 2 26 12 16 30 6 12Z" fill="url(#g)"/><path d="M16 2 26 12 16 14 6 12Z" fill="#fff" opacity=".35"/><path d="M16 14 26 12 16 30Z" fill="#000" opacity=".18"/></svg>
  <div class="title"><h1>Void &amp; Draconic</h1><small>SERVER-KONSOLE</small></div>
  <form method="post" action="/auth/login" id="f" autocomplete="on">
    __MSG__
    <input type="hidden" name="next" value="__NEXT__">
    <label class="f" for="user">Benutzer
      <input type="text" id="user" name="username" autocomplete="username" autocapitalize="off" spellcheck="false" required value="__USER__" __AF_USER__></label>
    <label class="f" for="pass">Passwort
      <span class="pw"><input type="password" id="pass" name="password" autocomplete="current-password" required __AF_PASS__>
      <button class="eye" type="button" id="eye" aria-label="Passwort anzeigen" aria-pressed="false">zeigen</button></span></label>
    <label class="remember" for="remember"><input type="checkbox" id="remember" name="remember" value="1" __REMEMBER__>
      <span>Angemeldet bleiben<small>30 Tage auf diesem Gerät</small></span></label>
    <button class="go" type="submit" id="go">Anmelden</button>
  </form>
  <div class="foot">mc-void-draconic.duckdns.org · <b>nur für die Crew</b></div>
</main>
<script>
const eye = document.getElementById("eye"), pw = document.getElementById("pass");
eye.addEventListener("click", () => { const show = pw.type === "password"; pw.type = show ? "text" : "password"; eye.textContent = show ? "verbergen" : "zeigen"; eye.setAttribute("aria-pressed", show); pw.focus(); });
document.getElementById("f").addEventListener("submit", () => { const b = document.getElementById("go"); b.disabled = true; b.textContent = "Prüfe …"; });
try { const r = localStorage.getItem("vd-remember"); if (r !== null && !__HAS_MSG__) document.getElementById("remember").checked = r === "1"; } catch (e) {}
document.getElementById("remember").addEventListener("change", e => { try { localStorage.setItem("vd-remember", e.target.checked ? "1" : "0"); } catch (x) {} });
(function sky() {
  const c = document.getElementById("sky"), x = c.getContext("2d"); let s = [];
  function size() { c.width = innerWidth * devicePixelRatio; c.height = innerHeight * devicePixelRatio;
    s = Array.from({length: 120}, () => ({x: Math.random() * c.width, y: Math.random() * c.height, r: (Math.random() * 1.2 + .3) * devicePixelRatio, p: Math.random() * 6.3})); }
  function draw(t) { x.clearRect(0, 0, c.width, c.height);
    for (const p of s) { x.globalAlpha = .25 + .45 * (.5 + .5 * Math.sin(t / 1400 + p.p)); x.fillStyle = "#d9c8ff"; x.beginPath(); x.arc(p.x, p.y, p.r, 0, 7); x.fill(); }
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) requestAnimationFrame(draw); }
  size(); addEventListener("resize", size); requestAnimationFrame(draw);
})();
</script>
</body>
</html>"""


def page(msg="", kind="err", nxt="/", user="", remember=True):
    box = f'<div class="msg {kind}" role="alert">{html.escape(msg)}</div>' if msg else ""
    return (PAGE.replace("__MSG__", box).replace("__NEXT__", html.escape(nxt, quote=True))
            .replace("__USER__", html.escape(user, quote=True))
            .replace("__AF_USER__", "" if user else "autofocus").replace("__AF_PASS__", "autofocus" if user else "")
            .replace("__REMEMBER__", "checked" if remember else "").replace("__HAS_MSG__", "true" if msg else "false"))


class H(BaseHTTPRequestHandler):
    server_version = "vd-auth"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass  # keine Zugangsdaten oder IPs ins Journal

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def client(self):
        return self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/auth/check":
            if valid(self.headers.get("Cookie")):
                return self.send(204)
            uri = self.headers.get("X-Forwarded-Uri", "/")
            if uri.startswith("/data/"):
                return self.send(401, b"Bitte anmelden", "text/plain; charset=utf-8")
            return self.send(302, headers=[("Location", "/auth/login?next=" + urllib.parse.quote(safe_next(uri)))])
        if u.path == "/auth/login":
            if valid(self.headers.get("Cookie")):
                return self.send(302, headers=[("Location", safe_next(q.get("next", ["/"])[0]))])
            msg = "Abgemeldet." if q.get("bye") else ""
            return self.send(200, page(msg, "ok", safe_next(q.get("next", ["/"])[0])).encode())
        if u.path == "/auth/logout":
            return self.send(302, headers=[("Location", "/auth/login?bye=1"),
                                           ("Set-Cookie", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax")])
        self.send(404, b"Nicht gefunden", "text/plain; charset=utf-8")

    do_HEAD = do_GET

    def api(self, path):
        """Kleine Steuer-API für angemeldete Nutzer. Nur JSON (Schutz gegen fremde Formulare), feste Felder."""
        if not valid(self.headers.get("Cookie")):
            return self.send(401, b'{"error":"Bitte anmelden"}', "application/json")
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send(415, b'{"error":"Nur JSON"}', "application/json")
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send(400, '{"error":"Ungültiges JSON"}'.encode(), "application/json")
        now = int(time.time())
        if path == "/api/pregen/watch" and isinstance(body.get("watch"), bool):
            data, name = {"watch_players": body["watch"], "updated": now}, "pregen-settings.json"
        elif path == "/api/pregen/plan" and isinstance(body.get("radii"), dict):
            radii = {k: max(0, min(100000, int(v))) for k, v in body["radii"].items() if k in DIMS and isinstance(v, (int, float))}
            data, name = {"radii": radii, "shape": "circle" if body.get("shape") == "circle" else "square",
                          "blocks": max(0, min(100, int(body.get("blocks") or 0))), "sent": now}, "pregen-plan.json"
        else:
            return self.send(400, b'{"error":"Unbekannte Anfrage"}', "application/json")
        tmp = os.path.join(CONTROL, "." + name)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, os.path.join(CONTROL, name))
        self.send(200, json.dumps({"ok": True, **data}).encode(), "application/json")

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/api/"):
            return self.api(path)
        if path != "/auth/login":
            return self.send(404, b"", "text/plain")
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        f = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        user = f.get("username", [""])[0].strip()
        pw = f.get("password", [""])[0]
        nxt = safe_next(f.get("next", ["/"])[0])
        remember = f.get("remember", [""])[0] == "1"
        ip, now = self.client(), time.time()
        fails = [t for t in FAILS.get(ip, []) if now - t < LOCK_FOR]
        if len(fails) >= LOCK_AFTER:
            wait = int(LOCK_FOR - (now - fails[0])) // 60 + 1
            return self.send(429, page(f"Zu viele Fehlversuche. Bitte in {wait} Min. erneut versuchen.", "err", nxt, user, remember).encode())
        good_user, good_hash = creds()
        ok = bool(good_hash) and hmac.compare_digest(user.lower(), good_user.lower())
        try:
            ok = bcrypt.checkpw(pw.encode(), good_hash.encode()) and ok
        except ValueError:
            ok = False
        if not ok:
            FAILS[ip] = fails + [now]
            time.sleep(0.5)
            left = LOCK_AFTER - len(FAILS[ip])
            hint = f" Noch {left} Versuche." if 0 < left < 3 else ""
            return self.send(401, page("Benutzer oder Passwort stimmt nicht." + hint, "err", nxt, user, remember).encode())
        FAILS.pop(ip, None)
        life = REMEMBER if remember else SESSION
        cookie = f"{COOKIE}={sign(good_user, int(now + life))}; Path=/; HttpOnly; Secure; SameSite=Lax"
        if remember:
            cookie += f"; Max-Age={REMEMBER}"
        self.send(303, headers=[("Location", nxt), ("Set-Cookie", cookie)])


if __name__ == "__main__":
    secret()
    ThreadingHTTPServer(("127.0.0.1", 8790), H).serve_forever()
