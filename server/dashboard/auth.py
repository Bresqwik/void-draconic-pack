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
  POST /api/pregen/run    {"run": true|false}  Vorgenerierung fortsetzen/stoppen (nur Admin)
  POST /api/pregen/plan  {"radii": {...}, "shape": "square"}  Plan aus dem Pregen-Rechner (wird erst nach Absprache eingeplant)
  GET  /auth/me           {"user": ..., "admin": true|false}
  GET/POST /auth/register Konto selbst anlegen (Name + Passwort). Das Konto wartet, bis ein Admin es freischaltet,
                          und hat nie Admin-Rechte. Gespeichert in users.json im StateDirectory (nur bcrypt-Hash).
Admins sind die Admin-Konten aus /etc/caddy/dashboard.env plus registrierte Konten, deren Name in ADMIN_NAMES steht
(z. B. "ADMIN_NAMES=stman476"; auch die brauchen die Freischaltung).
Crew-Zugang: VIEW_HASH (gesetzt mit "dashboard-crew-passwort") ist ein gemeinsames Passwort. Jeder meldet sich mit
seinem eigenen Namen an (nur ansehen). Namen fester Konten (DASH_USER, ADMIN:…) gehen nur mit deren eigenem Passwort.
Nur für Admin-Konten (Zeilen "ADMIN:<name>=<hash>", gesetzt mit "dashboard-admin"; altes Format ADMIN_USER/ADMIN_HASH geht weiter):
  POST /api/player        {"player": "Name", "action": "kick|op|deop|spawn|heal|clear|death|bring|goto|msg", "text": "..."}
  GET  /api/admin/log     letzte Spieler-Aktionen mit Ergebnis
  GET  /api/testhub[/run|/errors|/bericht]  Test-Hub (Testmaschinen, nur Admins); POST /api/testhub/push|bericht mit
                          Geräte-Token (siehe testhub.py; alte Adressen /api/rezepttest/* gehen weiter)
  GET  /api/admin/waechter  Server-Wächter: Messung, offene Probleme, Verlauf (aus /var/lib/mc-claude/waechter.json)
  POST /api/lag           {"action": "archive|restore|delete", "key": "<zeit_ms>-<Spieler>"}  Lag-Meldung archivieren/löschen
  POST /api/meldung      dasselbe für /meldung-Meldungen
  POST /api/chat          {"text": "..."}  Nachricht in den Minecraft-Chat (jedes Konto, als „[Web] <Name>“)
  POST /api/power         {"action": "start|stop|restart|stop_empty|restart_empty|restart_vote|cancel"}  Server-Knöpfe
  POST /api/pregen/watch, /api/pregen/plan  (seit der Registrierung ebenfalls nur Admin)
  GET  /api/admin/users   registrierte Konten (ohne Hashes)
  POST /api/admin/users   {"action": "approve|block|unblock|delete", "name": "..."}
Die API schreibt nur nach /var/lib/mc-dashboard/control, der Datensammler (root, RCON) liest dort und führt aus.
"""
import base64, hashlib, hmac, html, json, os, re, secrets, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bcrypt

ENV = "/etc/caddy/dashboard.env"
STATE = os.environ.get("STATE_DIRECTORY", "/var/lib/mc-dashboard-auth")
SECRET_FILE = os.path.join(STATE, "secret")
USERS_FILE = os.path.join(STATE, "users.json")
USERS_LOCK = threading.Lock()
NAME_RE = r"[A-Za-z0-9_.-]{3,20}"
REG_IPS, REG_PER_HOUR, MAX_PENDING = {}, 3, 30
USER_ACTIONS = {"approve", "block", "unblock", "delete"}
COOKIE = "vd_session"
REMEMBER = 30 * 86400      # "Angemeldet bleiben"
SESSION = 12 * 3600        # ohne Haken: Browser-Sitzung, spätestens nach 12 Stunden neu anmelden
FAILS, LOCK_AFTER, LOCK_FOR = {}, 5, 300
CONTROL = "/var/lib/mc-dashboard/control"
DIMS = {"ow", "ne", "end", "ae", "tf", "os"}
ACTIONS = {"kick", "op", "deop", "spawn", "heal", "msg", "clear", "death", "bring", "goto"}
LAG_ACTIONS = {"archive", "restore", "delete"}
POWER_ACTIONS = {"start", "stop", "restart", "stop_empty", "restart_empty", "restart_vote", "cancel"}
CHAT_LAST = {}             # Konto -> Zeit der letzten Chat-Nachricht (gegen Spam)


def env():
    d = {}
    try:
        for line in open(ENV, encoding="utf-8"):
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                d[k] = v
    except OSError:
        pass
    return d


def creds():
    d = env()
    return d.get("DASH_USER", ""), d.get("DASH_HASH", "")


def accounts():
    """{benutzer (klein): (anzeigename, hash, admin)}: gemeinsames Crew-Konto plus die Admin-Konten (Stefan, Mero …)."""
    d, acc = env(), {}
    if d.get("DASH_USER") and d.get("DASH_HASH"):
        # DASH_ADMIN=1: das Hauptkonto ist Stefans eigenes (nicht geteilt) und hat Admin-Rechte
        acc[d["DASH_USER"].lower()] = (d["DASH_USER"], d["DASH_HASH"], d.get("DASH_ADMIN") == "1")
    if d.get("ADMIN_USER") and d.get("ADMIN_HASH"):
        acc[d["ADMIN_USER"].lower()] = (d["ADMIN_USER"], d["ADMIN_HASH"], True)
    for k, v in d.items():
        if k.startswith("ADMIN:") and len(k) > 6 and v:
            acc[k[6:].lower()] = (k[6:], v, True)
    admin_names = {n.strip().lower() for n in d.get("ADMIN_NAMES", "").split(",") if n.strip()}
    for low, u in users().items():
        if u.get("status") == "active" and low not in acc:
            acc[low] = (u["name"], u["hash"], low in admin_names)
    return acc


def users():
    """Selbst registrierte Konten: {name (klein): {"name", "hash", "status": pending|active|blocked, "created", ...}}"""
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_users(u):
    tmp = USERS_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False, indent=1)
    os.replace(tmp, USERS_FILE)


def env_names():
    """Namen, die in dashboard.env vergeben sind (Hauptkonto, Admin-Konten) – nicht registrierbar."""
    d = env()
    names = {d.get("DASH_USER", "").lower(), d.get("ADMIN_USER", "").lower()}
    names |= {k[6:].lower() for k in d if k.startswith("ADMIN:")}
    return {n for n in names if n}


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
    # Die Passwort-Hashes gehören zum Schlüssel: neues Passwort = alle alten Sitzungen ungültig
    d = env()
    admins = "".join(v for k, v in sorted(d.items()) if k.startswith("ADMIN:"))
    return hashlib.sha256(secret() + d.get("DASH_HASH", "").encode() + d.get("ADMIN_HASH", "").encode() + admins.encode()
                          + d.get("VIEW_HASH", "").encode()).digest()


def ukey(user):
    u = users().get((user or "").lower())
    return key() + (u["hash"].encode() if u and (user or "").lower() not in env_names() else b"")


def sign(user, exp):
    body = base64.urlsafe_b64encode(f"{user}|{exp}".encode()).decode().rstrip("=")
    mac = hmac.new(ukey(user), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def valid(cookie_header):
    """Gibt den angemeldeten Benutzer zurück (oder None)."""
    for part in (cookie_header or "").split(";"):
        name, _, val = part.strip().partition("=")
        if name != COOKIE or "." not in val:
            continue
        body, mac = val.rsplit(".", 1)
        try:
            user, exp = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode().split("|")
        except ValueError:
            continue
        if not hmac.compare_digest(mac, hmac.new(ukey(user), body.encode(), hashlib.sha256).hexdigest()):
            continue
        if int(exp) > time.time() and (user.lower() in accounts() or crew_name(user)):
            return user
    return None


def crew_name(user):
    """Gültiger Crew-Name (gemeinsames Passwort aktiv, kein fester Kontoname)."""
    return (bool(env().get("VIEW_HASH")) and bool(re.fullmatch(r"[A-Za-z0-9_.-]{2,20}", user or ""))
            and user.lower() not in accounts() and user.lower() not in users())


def is_admin(user):
    a = accounts().get((user or "").lower())
    return bool(a and a[2])


def safe_next(n):
    n = n or "/"
    return n if n.startswith("/") and not n.startswith("//") and not n.startswith("/auth/") else "/"


PAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#07050F">
<title>__TITLE__ · Void &amp; Draconic Server-Konsole</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%23140A26'/%3E%3Cpath d='M8 2l4 4-4 8-4-8z' fill='%23B98CFF'/%3E%3Cpath d='M8 2l4 4-4 8z' fill='%23FF6A2B'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@600;800&family=Rethink+Sans:wght@400;500;600;700&family=Martian+Mono:wght@400;600&display=swap">
<style>
/* Gleiche Welt wie die Server-Konsole und das README: Void-Nebel, leuchtendes Portal, eine Glas-Karte mit Verlaufsrand. Hintergrund statisch. */
:root{
  color-scheme:dark;
  --void:#07050F; --line:rgba(185,140,255,.2); --line-strong:rgba(185,140,255,.5);
  --ink:#EEEAF8; --muted:#A69DC2; --violet:#7B3FE4; --violet-soft:#B98CFF; --lav:#C9A7FF; --ember:#FF6A2B; --ember-soft:#FFB27A; --cyan:#45DBE9; --red:#FF5D66; --green:#5FD672; --gold:#F5D547;
  --title:linear-gradient(90deg,#C9A7FF 0%,#E9DDFF 28%,#FFFFFF 46%,#FFE3CF 62%,#FFB27A 80%,#FF6A2B 100%);
  --edge:linear-gradient(140deg,rgba(201,167,255,.6),rgba(123,63,228,.2) 36%,rgba(123,63,228,.1) 64%,rgba(255,106,43,.5));
  --display:"Unbounded","Arial Black",system-ui,sans-serif;
  --body:"Rethink Sans","Segoe UI",system-ui,sans-serif;
  --mono:"Martian Mono",Consolas,ui-monospace,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{background:var(--void);color:var(--ink);font:15px/1.5 var(--body);min-height:100vh;display:grid;place-items:center;padding:28px 16px;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;
  background:radial-gradient(46% 40% at 50% 26%,rgba(123,63,228,.34),transparent 70%),
             radial-gradient(38% 34% at 96% 8%,rgba(255,106,43,.18),transparent 70%),
             radial-gradient(40% 36% at 4% 94%,rgba(123,63,228,.18),transparent 70%),
             radial-gradient(42% 38% at 92% 98%,rgba(69,219,233,.07),transparent 70%)}
body::after{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(120% 90% at 50% 35%,transparent 58%,rgba(0,0,0,.6))}
#sky{position:fixed;inset:0;width:100%;height:100%;pointer-events:none}
main{position:relative;z-index:1;width:100%;max-width:410px;display:grid;gap:18px;justify-items:center}
.portal{width:150px;height:150px;margin:-8px 0 -14px;overflow:visible}
.title{text-align:center;display:grid;gap:9px;justify-items:center}
.kicker{display:flex;align-items:center;gap:10px;font:600 10px/1 var(--mono);letter-spacing:.3em;text-transform:uppercase;color:var(--muted)}
.kicker i{width:22px;height:1px;background:linear-gradient(90deg,transparent,var(--lav))}
.kicker i:last-child{background:linear-gradient(90deg,var(--lav),transparent)}
h1{font:800 clamp(24px,7.4vw,33px)/1.05 var(--display);margin:0;letter-spacing:.02em;text-transform:uppercase;
  background:var(--title);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 18px rgba(123,63,228,.6))}
h1 .amp{background:linear-gradient(180deg,#F5D547,#FF6A2B);-webkit-background-clip:text;background-clip:text;color:transparent}
.title small{display:flex;align-items:center;gap:10px;font:600 11px/1 var(--mono);letter-spacing:.24em;color:var(--lav)}
.title small b{color:var(--ember);font-weight:700}
.title small .sep{width:5px;height:5px;transform:rotate(45deg);background:var(--ember-soft);opacity:.75}
form{position:relative;width:100%;border:1px solid transparent;border-radius:22px;padding:22px 22px 24px;display:grid;gap:16px;overflow:hidden;
  background:radial-gradient(120% 60% at 0% 0%,rgba(123,63,228,.24),transparent 60%) padding-box,radial-gradient(90% 60% at 100% 100%,rgba(255,106,43,.12),transparent 60%) padding-box,
    linear-gradient(180deg,rgba(29,15,53,.88),rgba(12,7,24,.9)) padding-box,var(--edge) border-box;
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:0 30px 80px -20px rgba(0,0,0,.7),0 0 60px -24px rgba(123,63,228,.8)}
form::before{content:"";position:absolute;top:0;left:26px;right:26px;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.32) 30%,transparent)}
.fh{display:flex;align-items:center;gap:12px;margin-bottom:2px}
.fh .ft{font:800 13px/1 var(--display);letter-spacing:.06em;text-transform:uppercase;background:linear-gradient(90deg,#E4D4FF,#FFFFFF 55%,#FFD7BA);-webkit-background-clip:text;background-clip:text;color:transparent}
.fh i{flex:1;height:1px;background:linear-gradient(90deg,rgba(201,167,255,.8),rgba(123,63,228,.6) 55%,rgba(255,106,43,.55));box-shadow:0 0 7px rgba(123,63,228,.8);opacity:.75}
.hx{position:relative;flex:none;display:grid;place-items:center;width:31px;height:36px;filter:drop-shadow(0 0 6px rgba(123,63,228,.75))}
.hx::before,.hx::after{content:"";position:absolute;inset:0;clip-path:polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%)}
.hx::before{background:linear-gradient(135deg,#C9A7FF,#7B3FE4 55%,#FF6A2B)}
.hx::after{inset:1.6px;background:radial-gradient(circle at 50% 38%,#3A1C78,#140A26 70%,#07050F)}
.hx svg{position:relative;z-index:1;width:17px;height:17px;fill:none;stroke:#EEEAF8;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.hx svg .a{stroke:#FFB27A}
label.f{display:grid;gap:8px;font:600 10.5px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
input[type=text],input[type=password]{width:100%;font:500 16px var(--body);color:var(--ink);background:rgba(7,5,15,.62);border:1px solid var(--line);
  border-radius:12px;padding:12px 14px;transition:border-color .2s,box-shadow .2s;letter-spacing:normal;text-transform:none;box-shadow:inset 0 1px 2px rgba(0,0,0,.35)}
input[type=text]:hover,input[type=password]:hover{border-color:rgba(185,140,255,.34)}
input[type=text]:focus,input[type=password]:focus{outline:none;border-color:var(--violet-soft);box-shadow:0 0 0 3px rgba(123,63,228,.32),0 0 22px -6px rgba(123,63,228,.8)}
.pw{position:relative}
.pw input{padding-right:104px}
.eye{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:rgba(185,140,255,.08);border:1px solid var(--line);color:var(--muted);cursor:pointer;padding:6px 9px;border-radius:9px;font:600 11px var(--mono);letter-spacing:.02em;text-transform:none}
.eye:hover{color:var(--ink);border-color:var(--line-strong)}
.remember{display:flex;align-items:center;gap:12px;font-size:14px;color:var(--ink);cursor:pointer;user-select:none}
.remember input{width:18px;height:18px;accent-color:var(--violet);margin:0}
.remember span small{display:block;color:var(--muted);font-size:12.5px}
button.go{position:relative;font:800 14px/1 var(--display);letter-spacing:.06em;text-transform:uppercase;color:#fff;border:0;border-radius:13px;padding:16px;cursor:pointer;
  background:linear-gradient(110deg,var(--violet),#B05CE8 55%,var(--ember));box-shadow:0 12px 30px -10px rgba(255,106,43,.55),0 0 30px -8px rgba(123,63,228,.8),inset 0 1px 0 rgba(255,255,255,.25);transition:transform .15s,filter .2s}
button.go:hover{filter:brightness(1.12)}
button.go:active{transform:translateY(1px)}
button.go[disabled]{filter:grayscale(.5) brightness(.8);cursor:wait}
:focus-visible{outline:2px solid var(--cyan);outline-offset:3px}
.msg{font-size:14px;border-radius:11px;padding:10px 12px;border:1px solid}
.msg.err{color:#ff8f96;border-color:rgba(255,93,102,.45);background:rgba(255,93,102,.09)}
.msg.ok{color:var(--green);border-color:rgba(95,214,114,.4);background:rgba(95,214,114,.08)}
.alt{font-size:14px;color:var(--muted);text-align:center}
.alt a{color:var(--violet-soft);font-weight:600;text-decoration:none;border-bottom:1px solid rgba(185,140,255,.4)}
.alt a:hover{color:var(--ink)}
.hint{font-size:12.5px;color:var(--muted);margin:-6px 0 0;line-height:1.45}
.foot{display:grid;gap:10px;justify-items:center;font:500 11px/1.5 var(--mono);color:var(--muted);text-align:center;letter-spacing:.04em}
.foot b{color:var(--violet-soft);font-weight:600;white-space:nowrap}
.div{display:flex;align-items:center;gap:10px;width:220px}
.div span{flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(201,167,255,.6))}
.div span:last-child{background:linear-gradient(90deg,rgba(255,106,43,.7),transparent)}
.div svg{width:12px;height:18px;filter:drop-shadow(0 0 6px rgba(123,63,228,.9))}
@media (max-width:420px){.portal{width:120px;height:120px}form{padding:20px 18px 22px}.kicker{font-size:9px;letter-spacing:.22em}}
@media (prefers-reduced-motion: reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<canvas id="sky" aria-hidden="true"></canvas>
<main>
  <svg class="portal" viewBox="0 0 140 140" aria-hidden="true">
    <defs>
      <radialGradient id="hpGlow" cx="70" cy="64" r="70" gradientUnits="userSpaceOnUse"><stop offset=".42" stop-color="#7B3FE4" stop-opacity=".85"/><stop offset=".7" stop-color="#7B3FE4" stop-opacity=".22"/><stop offset="1" stop-color="#7B3FE4" stop-opacity="0"/></radialGradient>
      <radialGradient id="hpCore" cx="70" cy="64" r="40" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#000"/><stop offset=".5" stop-color="#07030F"/><stop offset=".8" stop-color="#2B1360"/><stop offset=".95" stop-color="#7B3FE4"/><stop offset="1" stop-color="#C9A7FF"/></radialGradient>
      <linearGradient id="hpRing" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#C9A7FF"/><stop offset=".5" stop-color="#7B3FE4"/><stop offset="1" stop-color="#45DBE9"/></linearGradient>
      <linearGradient id="hpCL" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F1E6FF"/><stop offset=".45" stop-color="#A97BF5"/><stop offset="1" stop-color="#4A2399"/></linearGradient>
      <linearGradient id="hpCD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9A66F0"/><stop offset=".5" stop-color="#3E1C85"/><stop offset="1" stop-color="#170A33"/></linearGradient>
      <radialGradient id="hpFloor" cx="70" cy="131" r="38" gradientUnits="userSpaceOnUse" gradientTransform="translate(0 131) scale(1 .18) translate(0 -131)"><stop offset="0" stop-color="#fff" stop-opacity=".8"/><stop offset=".3" stop-color="#C9A7FF" stop-opacity=".55"/><stop offset="1" stop-color="#7B3FE4" stop-opacity="0"/></radialGradient>
    </defs>
    <circle cx="70" cy="64" r="70" fill="url(#hpGlow)"/>
    <circle cx="70" cy="64" r="54" fill="none" stroke="#C9A7FF" stroke-opacity=".32" stroke-dasharray="1 5"/>
    <circle cx="70" cy="64" r="47" fill="none" stroke="#7B3FE4" stroke-opacity=".55"/>
    <circle cx="70" cy="64" r="40" fill="url(#hpCore)"/>
    <g fill="none" stroke-linecap="round">
      <path d="M70 32a32 32 0 0 1 30 22" stroke="#C9A7FF" stroke-opacity=".6" stroke-width="1.6"/>
      <path d="M44 82a31 31 0 0 1-6-28" stroke="#B98CFF" stroke-opacity=".5" stroke-width="1.4"/>
      <path d="M71 44a20 20 0 0 1 19 15" stroke="#E9DDFF" stroke-opacity=".55" stroke-width="1.2"/>
      <path d="M57 76a18 18 0 0 1-5-14" stroke="#C9A7FF" stroke-opacity=".45" stroke-width="1.1"/>
      <path d="M84 92a30 30 0 0 1-28 3" stroke="#45DBE9" stroke-opacity=".4" stroke-width="1.3"/>
      <path d="M66 58a8 8 0 0 1 10 4" stroke="#fff" stroke-opacity=".35" stroke-width="1"/>
    </g>
    <circle cx="70" cy="64" r="40" fill="none" stroke="url(#hpRing)" stroke-width="2.4"/>
    <ellipse cx="70" cy="131" rx="38" ry="7" fill="url(#hpFloor)"/>
    <path d="M46 104 41 116 45 131 49 131Z" fill="url(#hpCL)"/><path d="M46 104 52 116 49 131Z" fill="url(#hpCD)"/>
    <path d="M94 100 88 113 91 131 95 131Z" fill="url(#hpCL)"/><path d="M94 100 100 113 95 131Z" fill="url(#hpCD)"/>
    <path d="M58 98 53 112 56 131 60 131Z" fill="url(#hpCL)"/><path d="M58 98 64 112 60 131Z" fill="url(#hpCD)"/>
    <path d="M70 84 62 102 66 131 70 131Z" fill="url(#hpCL)"/><path d="M70 84 78 102 74 131 70 131Z" fill="url(#hpCD)"/>
    <path d="M70 84 62 102 70 106 78 102Z" fill="#fff" opacity=".22"/>
    <path d="M82 96 77 110 80 131 84 131Z" fill="url(#hpCL)"/><path d="M82 96 88 110 84 131Z" fill="url(#hpCD)"/>
    <path d="M22 30l1.2 3.2 3.2 1.2-3.2 1.2L22 38.8l-1.2-3.2-3.2-1.2 3.2-1.2Z" fill="#E9DDFF" opacity=".8"/>
    <path d="M118 22l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8Z" fill="#FFB27A" opacity=".8"/>
  </svg>
  <div class="title"><div class="kicker" aria-hidden="true"><i></i>Minecraft · Modpack<i></i></div><h1>Void <span class="amp">&amp;</span> Draconic</h1><small><b aria-hidden="true">›</b>SERVER-KONSOLE</small></div>
__FORM__
  <div class="alt">__ALT__</div>
  <div class="foot"><div class="div" aria-hidden="true"><span></span><svg viewBox="0 0 16 24"><polygon points="8,0 15,12 8,24 1,12" fill="#7B3FE4"/><polygon points="8,0 8,24 1,12" fill="#C9A7FF"/></svg><span></span></div>
    <div>mc-void-draconic.duckdns.org · <b>nur für die Crew</b></div></div>
</main>
<script>
const eye = document.getElementById("eye"), pw = document.getElementById("pass"), pw2 = document.getElementById("pass2"), rem = document.getElementById("remember");
eye?.addEventListener("click", () => { const show = pw.type === "password"; pw.type = show ? "text" : "password"; if (pw2) pw2.type = pw.type;
  eye.textContent = show ? "verbergen" : "zeigen"; eye.setAttribute("aria-pressed", show); pw.focus(); });
document.getElementById("f")?.addEventListener("submit", e => {
  if (pw2 && pw2.value !== pw.value) { e.preventDefault(); pw2.setCustomValidity("Passwörter stimmen nicht überein"); pw2.reportValidity(); return; }
  const b = document.getElementById("go"); b.disabled = true; b.textContent = "Prüfe …"; });
pw2?.addEventListener("input", () => pw2.setCustomValidity(""));
try { const r = localStorage.getItem("vd-remember"); if (rem && r !== null && !__HAS_MSG__) rem.checked = r === "1"; } catch (e) {}
rem?.addEventListener("change", e => { try { localStorage.setItem("vd-remember", e.target.checked ? "1" : "0"); } catch (x) {} });
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


LOGIN_FORM = """  <form method="post" action="/auth/login" id="f" autocomplete="on">
    <div class="fh" aria-hidden="true"><span class="hx"><svg viewBox="0 0 24 24"><rect x="5" y="10.5" width="14" height="10" rx="2.2"/><path class="a" d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/><path class="a" d="M12 14.5v2.5"/></svg></span><span class="ft">Anmelden</span><i></i></div>
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
"""
REGISTER_FORM = """  <form method="post" action="/auth/register" id="f" autocomplete="on">
    <div class="fh" aria-hidden="true"><span class="hx"><svg viewBox="0 0 24 24"><circle cx="10" cy="8" r="3.5"/><path d="M3.5 20a6.5 6.5 0 0 1 13 0"/><path class="a" d="M19 8v6M16 11h6"/></svg></span><span class="ft">Konto erstellen</span><i></i></div>
    __MSG__
    <p class="hint">Am besten deinen Minecraft-Namen nehmen. Ein Admin schaltet das Konto frei, danach kannst du dich anmelden.</p>
    <label class="f" for="user">Benutzername
      <input type="text" id="user" name="username" autocomplete="username" autocapitalize="off" spellcheck="false" required minlength="3" maxlength="20" title="3–20 Zeichen: Buchstaben, Ziffern, Punkt, Strich, Unterstrich" value="__USER__" __AF_USER__></label>
    <label class="f" for="pass">Passwort <span style="text-transform:none;letter-spacing:0">(mind. 8 Zeichen)</span>
      <span class="pw"><input type="password" id="pass" name="password" autocomplete="new-password" required minlength="8" maxlength="128">
      <button class="eye" type="button" id="eye" aria-label="Passwort anzeigen" aria-pressed="false">zeigen</button></span></label>
    <label class="f" for="pass2">Passwort wiederholen
      <input type="password" id="pass2" name="password2" autocomplete="new-password" required minlength="8" maxlength="128"></label>
    <button class="go" type="submit" id="go">Konto erstellen</button>
  </form>
"""
DONE_FORM = """  <form id="f" action="/auth/login" method="get">
    <div class="fh" aria-hidden="true"><span class="hx"><svg viewBox="0 0 24 24"><path class="a" d="M5 12.5l4.5 4.5L19 7.5"/></svg></span><span class="ft">Konto angelegt</span><i></i></div>
    __MSG__
    <button class="go" type="submit" id="go">Zur Anmeldung</button>
  </form>
"""
FORMS = {"login": ("Anmelden", LOGIN_FORM, 'Noch kein Konto? <a href="/auth/register">Konto erstellen</a>'),
         "register": ("Konto erstellen", REGISTER_FORM, 'Schon ein Konto? <a href="/auth/login">Anmelden</a>'),
         "done": ("Konto angelegt", DONE_FORM, "")}


def page(msg="", kind="err", nxt="/", user="", remember=True, form="login"):
    box = f'<div class="msg {kind}" role="alert">{html.escape(msg)}</div>' if msg else ""
    title, body, alt = FORMS[form]
    return (PAGE.replace("__TITLE__", title).replace("__FORM__", body).replace("__ALT__", alt)
            .replace("__MSG__", box).replace("__NEXT__", html.escape(nxt, quote=True))
            .replace("__USER__", html.escape(user, quote=True))
            .replace("__AF_USER__", "" if user else "autofocus").replace("__AF_PASS__", "autofocus" if user else "")
            .replace("__REMEMBER__", "checked" if remember else "").replace("__HAS_MSG__", "true" if msg else "false"))


# Test-Hub (Testmaschinen MacBook/Windows → /admin/testhub/): Logik in testhub.py, Daten in STATE/testhub/.
import testhub


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
        if u.path == "/auth/admincheck":
            # Admin-Erweiterungen unter /admin/ (z. B. 3D-Erzverarbeitung): nur Admin-Konten
            user = valid(self.headers.get("Cookie"))
            if user and is_admin(user):
                return self.send(204)
            if user:
                return self.send(403, "Nur für Admin-Konten.".encode(), "text/plain; charset=utf-8")
            uri = self.headers.get("X-Forwarded-Uri", "/")
            return self.send(302, headers=[("Location", "/auth/login?next=" + urllib.parse.quote(safe_next(uri)))])
        if u.path == "/auth/login":
            if valid(self.headers.get("Cookie")):
                return self.send(302, headers=[("Location", safe_next(q.get("next", ["/"])[0]))])
            msg = "Abgemeldet." if q.get("bye") else ""
            return self.send(200, page(msg, "ok", safe_next(q.get("next", ["/"])[0])).encode())
        if u.path == "/auth/me":
            user = valid(self.headers.get("Cookie"))
            if not user:
                return self.send(401, b'{"error":"Bitte anmelden"}', "application/json")
            return self.send(200, json.dumps({"user": user, "admin": is_admin(user)}).encode(), "application/json")
        if u.path == "/auth/register":
            if valid(self.headers.get("Cookie")):
                return self.send(302, headers=[("Location", "/")])
            return self.send(200, page(form="register").encode())
        if u.path == "/api/admin/users":
            if not is_admin(valid(self.headers.get("Cookie"))):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            admin_names = {n.strip().lower() for n in env().get("ADMIN_NAMES", "").split(",") if n.strip()}
            out = [{"name": v["name"], "status": v.get("status"), "created": v.get("created"), "by": v.get("by"),
                    "last_login": v.get("last_login"), "admin": k in admin_names} for k, v in users().items()]
            out.sort(key=lambda x: ({"pending": 0, "active": 1, "blocked": 2}.get(x["status"], 3), x["name"].lower()))
            return self.send(200, json.dumps(out).encode(), "application/json")
        if u.path == "/api/admin/log":
            if not is_admin(valid(self.headers.get("Cookie"))):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            try:
                data = open(os.path.join(CONTROL, "admin-log.json"), "rb").read()
            except OSError:
                data = b"[]"
            return self.send(200, data, "application/json")
        if u.path == "/api/admin/waechter":   # Server-Wächter (watch.py) – nur Admins
            if not is_admin(valid(self.headers.get("Cookie"))):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            try:
                data = open("/var/lib/mc-claude/waechter.json", "rb").read()
            except OSError:
                data = b"{}"
            return self.send(200, data, "application/json")
        if u.path.startswith("/api/testhub") or u.path == "/api/rezepttest":   # Test-Hub – nur Admins
            if not is_admin(valid(self.headers.get("Cookie"))):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            if u.path in ("/api/testhub", "/api/rezepttest"):
                return self.send(200, json.dumps(testhub.overview(), ensure_ascii=False).encode(), "application/json")
            if u.path == "/api/testhub/run":
                r = testhub.run(q.get("id", [""])[0])
                return self.send(200, json.dumps(r, ensure_ascii=False).encode(), "application/json") if r else self.send(404, b"{}", "application/json")
            if u.path == "/api/testhub/errors":
                return self.send(200, json.dumps(testhub.errors(q.get("run", [""])[0], q.get("from", ["0"])[0]),
                                                 ensure_ascii=False).encode(), "application/json")
            if u.path == "/api/testhub/bericht":
                data = testhub.bericht(q.get("run", [""])[0])
                return self.send(200, data, "application/json") if data else self.send(404, b'{"error":"kein Bericht"}', "application/json")
            return self.send(404, b"{}", "application/json")
        if u.path == "/auth/logout":
            return self.send(302, headers=[("Location", "/auth/login?bye=1"),
                                           ("Set-Cookie", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax")])
        self.send(404, b"Nicht gefunden", "text/plain; charset=utf-8")

    do_HEAD = do_GET

    def api(self, path):
        """Kleine Steuer-API für angemeldete Nutzer. Nur JSON (Schutz gegen fremde Formulare), feste Felder."""
        user = valid(self.headers.get("Cookie"))
        if not user:
            return self.send(401, b'{"error":"Bitte anmelden"}', "application/json")
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send(415, b'{"error":"Nur JSON"}', "application/json")
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send(400, '{"error":"Ungültiges JSON"}'.encode(), "application/json")
        now = int(time.time())
        if path in ("/api/pregen/watch", "/api/pregen/plan", "/api/admin/users") and not is_admin(user):
            return self.send(403, b'{"error":"Nur Admin"}', "application/json")
        if path == "/api/admin/users":
            return self.user_admin(user, body)
        if path == "/api/pregen/watch" and isinstance(body.get("watch"), bool):
            data, name = {"watch_players": body["watch"], "updated": now}, "pregen-settings.json"
        elif path == "/api/pregen/plan" and isinstance(body.get("radii"), dict):
            radii = {k: max(0, min(100000, int(v))) for k, v in body["radii"].items() if k in DIMS and isinstance(v, (int, float))}
            data, name = {"radii": radii, "shape": "circle" if body.get("shape") == "circle" else "square",
                          "blocks": max(0, min(100, int(body.get("blocks") or 0))), "sent": now}, "pregen-plan.json"
        elif path == "/api/pregen/run" and isinstance(body.get("run"), bool):
            # Vorgenerierung starten/stoppen: nur Admin, ausgeführt vom Datensammler
            if not is_admin(user):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            data, name = {"run": body["run"], "by": user, "time": now}, "pregen-run.json"
        elif path == "/api/player":
            # Spieler-Aktionen nur für das Admin-Konto; ausgeführt vom Datensammler per RCON
            if not is_admin(user):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            player, action = str(body.get("player", "")), str(body.get("action", ""))
            if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", player) or action not in ACTIONS:
                return self.send(400, b'{"error":"Spieler oder Aktion ungueltig"}', "application/json")
            text = re.sub(r"[\x00-\x1f]", " ", str(body.get("text") or ""))[:200]
            data, name = {"player": player, "action": action, "text": text, "by": user, "time": now,
                          "id": secrets.token_hex(6)}, f"action-{time.time_ns()}.json"
        elif path in ("/api/lag", "/api/meldung"):
            # Lag-Meldung archivieren, zurückholen oder löschen: nur Admin, ausgeführt vom Datensammler
            if not is_admin(user):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            action, k = str(body.get("action", "")), str(body.get("key", ""))
            if action not in LAG_ACTIONS or not re.fullmatch(r"\d{10,14}-[A-Za-z0-9_]{1,16}", k):
                return self.send(400, b'{"error":"Aktion oder Meldung ungueltig"}', "application/json")
            data, name = {"action": action, "key": k, "by": user, "time": now}, f"{'meld' if path.endswith('meldung') else 'lag'}-{time.time_ns()}.json"
        elif path == "/api/power":
            # Server starten/stoppen/neu starten: nur Admin; die Regel „nie mit Spielern online“ prüft der Datensammler
            if not is_admin(user):
                return self.send(403, b'{"error":"Nur Admin"}', "application/json")
            action = str(body.get("action", ""))
            if action not in POWER_ACTIONS:
                return self.send(400, b'{"error":"Aktion ungueltig"}', "application/json")
            data, name = {"action": action, "by": user, "time": now, "id": secrets.token_hex(6)}, f"power-{time.time_ns()}.json"
        elif path == "/api/chat":
            # Chat aus dem Dashboard: jedes angemeldete Konto (Crew mit eigenem Namen); der Datensammler schickt per tellraw
            text = re.sub(r"[\x00-\x1f]", " ", str(body.get("text") or "")).strip()[:200]
            if not text:
                return self.send(400, b'{"error":"Leere Nachricht"}', "application/json")
            if time.time() - CHAT_LAST.get(user.lower(), 0) < 1.5:
                return self.send(429, '{"error":"Bitte kurz warten"}'.encode(), "application/json")
            CHAT_LAST[user.lower()] = time.time()
            data, name = {"text": text, "by": user, "time": now, "id": secrets.token_hex(6)}, f"chat-{time.time_ns()}.json"
        else:
            return self.send(400, b'{"error":"Unbekannte Anfrage"}', "application/json")
        tmp = os.path.join(CONTROL, "." + name)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, os.path.join(CONTROL, name))
        self.send(200, json.dumps({"ok": True, **data}).encode(), "application/json")

    def user_admin(self, admin, body):
        """Registrierte Konten freischalten, sperren, entsperren oder löschen (nur Admin)."""
        action, name = str(body.get("action", "")), str(body.get("name", "")).lower()
        if action not in USER_ACTIONS or not re.fullmatch(NAME_RE, name):
            return self.send(400, b'{"error":"Aktion oder Name ungueltig"}', "application/json")
        if name == admin.lower():
            return self.send(400, '{"error":"Eigenes Konto nicht änderbar"}'.encode(), "application/json")
        with USERS_LOCK:
            u = users()
            if name not in u:
                return self.send(404, '{"error":"Konto nicht gefunden"}'.encode(), "application/json")
            if action == "delete":
                del u[name]
            else:
                u[name]["status"] = {"approve": "active", "unblock": "active", "block": "blocked"}[action]
                u[name]["by"] = admin
                u[name]["changed"] = int(time.time())
            save_users(u)
        self.send(200, json.dumps({"ok": True, "name": name, "action": action}).encode(), "application/json")

    def register(self):
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        f = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        user = f.get("username", [""])[0].strip()
        pw, pw2 = f.get("password", [""])[0], f.get("password2", [""])[0]
        ip, now = self.client(), time.time()
        err = lambda m, code=400: self.send(code, page(m, "err", user=user, form="register").encode())
        if not re.fullmatch(NAME_RE, user):
            return err("Benutzername: 3–20 Zeichen, nur Buchstaben, Ziffern, Punkt, Strich, Unterstrich.")
        if len(pw) < 8 or len(pw) > 128:
            return err("Das Passwort braucht mindestens 8 Zeichen.")
        if pw != pw2:
            return err("Die Passwörter stimmen nicht überein.")
        recent = [t for t in REG_IPS.get(ip, []) if now - t < 3600]
        if len(recent) >= REG_PER_HOUR:
            return err("Zu viele neue Konten von diesem Anschluss. Bitte später erneut versuchen.", 429)
        h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(12)).decode()
        with USERS_LOCK:
            u = users()
            low = user.lower()
            if low in u or low in env_names() or low in accounts():
                return err("Der Name ist schon vergeben.", 409)
            if sum(1 for v in u.values() if v.get("status") == "pending") >= MAX_PENDING:
                return err("Gerade warten zu viele Konten auf Freischaltung. Bitte später erneut versuchen.", 429)
            u[low] = {"name": user, "hash": h, "status": "pending", "created": int(now)}
            save_users(u)
        REG_IPS[ip] = recent + [now]
        self.send(200, page(f"Konto „{user}“ ist angelegt. Ein Admin muss es noch freischalten, danach kannst du dich anmelden.",
                            "ok", form="done").encode())

    def testhub_post(self, path):
        """Testmaschinen: eigenes Token (nur SHA-256 auf dem Server) statt Anmeldung."""
        device = testhub.device_for(self.headers.get("Authorization"))
        if not device:
            time.sleep(0.5)
            return self.send(403, b'{"error":"Token"}', "application/json")
        n = int(self.headers.get("Content-Length") or 0)
        bericht = path.endswith("/bericht")
        if n > (60_000_000 if bericht else 2_000_000):
            return self.send(413, b'{"error":"zu gross"}', "application/json")
        data = self.rfile.read(n) or b"{}"
        try:
            body = json.loads(data)
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.send(400, b'{"error":"JSON"}', "application/json")
        if bericht:
            rid = testhub.save_bericht(device, data)
        else:
            rid = testhub.push(device, body, "rezepttest" if path.startswith("/api/rezepttest") else "test")
        return self.send(200, json.dumps({"ok": True, "run": rid, "device": device}).encode(), "application/json")

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/api/testhub/push", "/api/testhub/bericht", "/api/rezepttest/push", "/api/rezepttest/bericht"):
            return self.testhub_post(path)
        if path.startswith("/api/"):
            return self.api(path)
        if path == "/auth/register":
            return self.register()
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
        acc = accounts().get(user.lower())
        reg = users().get(user.lower()) if not acc else None
        if acc:
            good_user, good_hash = acc[0], acc[1]
        elif reg:
            good_user, good_hash = reg["name"], reg["hash"]
        elif crew_name(user):
            good_user, good_hash = user, env().get("VIEW_HASH", "")  # eigener Name + gemeinsames Crew-Passwort
        else:
            good_user, good_hash = "", "$2b$12$" + "x" * 53  # gleiche Rechenzeit ohne gültigen Namen
        ok = bool(good_user)
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
        if reg:  # Passwort stimmt, Konto aber noch nicht frei oder gesperrt
            m = "Dein Konto wartet noch auf Freischaltung durch einen Admin." if reg.get("status") == "pending" else "Dieses Konto ist gesperrt."
            return self.send(403, page(m, "err", nxt, user, remember).encode())
        if users().get(good_user.lower()) and good_user.lower() not in env_names():
            with USERS_LOCK:
                u = users()
                if good_user.lower() in u:
                    u[good_user.lower()]["last_login"] = int(now)
                    save_users(u)
        life = REMEMBER if remember else SESSION
        cookie = f"{COOKIE}={sign(good_user, int(now + life))}; Path=/; HttpOnly; Secure; SameSite=Lax"
        if remember:
            cookie += f"; Max-Age={REMEMBER}"
        self.send(303, headers=[("Location", nxt), ("Set-Cookie", cookie)])


if __name__ == "__main__":
    secret()
    testhub.init(STATE)
    ThreadingHTTPServer(("127.0.0.1", 8790), H).serve_forever()
