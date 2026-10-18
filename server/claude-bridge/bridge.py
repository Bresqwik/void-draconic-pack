#!/usr/bin/env python3
"""Void & Draconic – Brücke zwischen dem Ingame-Befehl /claude und Claude Code (Dauerdienst mc-claude-bridge.service).

Der KubeJS-Befehl /claude legt Anfragen als JSON in /opt/void-draconic/claude-bridge/inbox ab. Dieser Dienst
  - verwaltet die Aufgabenliste selbst (/claude aufgabe add|list|done), ohne Claude zu fragen,
  - beantwortet /claude status aus den Dashboard-Daten,
  - gibt alles andere an Claude Code weiter: als Benutzer claudebot, ohne Werkzeuge (--tools ""), mit Stefans Abo.
Antworten gehen per RCON (tellraw) nur an den fragenden Spieler.

Anmeldung: Stefan legt den Token aus `claude setup-token` selbst in /etc/mc-claude/token.env ab
(eine Zeile CLAUDE_CODE_OAUTH_TOKEN=..., Rechte 600 root). Der Dienst gibt den Token nie aus.
Nur Python-Standardbibliothek.
"""
import glob, json, os, re, socket, struct, subprocess, time

MC = "/opt/void-draconic"
INBOX = os.path.join(MC, "claude-bridge", "inbox")
STATE = "/var/lib/mc-claude"
TASKS = os.path.join(STATE, "aufgaben.json")
HIST = os.path.join(STATE, "verlauf.json")
LOG = os.path.join(STATE, "bridge.log")
TOKEN_FILE = "/etc/mc-claude/token.env"
DASH = "/var/www/mc-dashboard/data"
CLAUDE = "/var/lib/claudebot/.local/bin/claude"
AS_BOT = ["setpriv", "--reuid=claudebot", "--regid=claudebot", "--init-groups"]
MODEL = "sonnet"
TIMEOUT = 240
PROJECT = "/var/lib/claudebot/projekt"     # Projektordner mit CLAUDE.md (Wissen, Regeln, Datenquellen)
SESSIONS = os.path.join(STATE, "sitzungen.json")   # Spieler -> Claude-Sitzungs-ID (fortlaufender Chat)
READ_DIRS = ["/var/www/mc-dashboard/data", "/var/lib/mc-claude", "/var/lib/mc-dashboard",
             "/opt/void-draconic/logs", "/opt/void-draconic/kubejs", "/opt/void-draconic/config"]
ALLOWED_UUIDS = {"bd84bd46-3360-43cc-9f4c-ff42e8f6356a"}   # stman476 – nur Stefan darf /claude nutzen
TOOLS = "Read,Grep,Glob"                   # nur lesen; Geheimnisse sind für claudebot ohnehin nicht lesbar

SYSTEM = """Du antwortest im Minecraft-Chat des Servers „Void & Draconic“. Regeln und Datenquellen stehen in CLAUDE.md
im Projektordner. Antworte auf Deutsch, kurz, ohne Markdown. Vorschläge für Maßnahmen als eigene Zeile „AKTION: …“,
Merkzettel als „AUFGABE: …“."""

ACTIONS = {"status": ("Status", "Aktuelle Wächter-Messwerte"), "leer": ("Neustart wenn leer", "Neustart, sobald niemand online ist"),
           "abstimmung": ("Neustart-Abstimmung", "Alle Online-Spieler fragen"), "stumm": ("Stumm", "Wächter-Meldungen stummschalten"),
           "laut": ("Laut", "Wächter-Meldungen wieder an")}


def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a) + "\n")


def read_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    tmp = path + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------- RCON ----------
def rcon(cmd):
    p = dict(l.rstrip("\n").split("=", 1) for l in open(os.path.join(MC, "server.properties"), encoding="utf-8")
             if "=" in l and not l.startswith("#"))
    s = socket.create_connection(("127.0.0.1", int(p["rcon.port"])), timeout=20)

    def pkt(i, t, body):
        b = body.encode("utf-8") + b"\0\0"
        s.sendall(struct.pack("<iii", len(b) + 8, i, t) + b)

    def rd():
        n = struct.unpack("<i", s.recv(4))[0]
        d = b""
        while len(d) < n:
            c = s.recv(n - len(d))
            if not c:
                break
            d += c
        return d[8:-2].decode("utf-8", "replace")

    try:
        pkt(1, 3, p["rcon.password"])
        rd()
        pkt(2, 2, cmd)
        return rd()
    finally:
        s.close()


def say(player, text, color="white"):
    """Text an einen Spieler, in Zeilen zu höchstens ~240 Zeichen (an Satz- oder Wortgrenzen)."""
    text = re.sub(r"[*_`#]+", "", text).strip()
    parts, cur = [], ""
    for word in re.split(r"(\s+)", text):
        if len(cur) + len(word) > 240 and cur.strip():
            parts.append(cur.strip())
            cur = ""
        cur += word
    if cur.strip():
        parts.append(cur.strip())
    for i, part in enumerate(parts[:8]):
        msg = [{"text": "[Claude] " if i == 0 else "  ", "color": "light_purple"}, {"text": part, "color": color}]
        try:
            rcon(f"tellraw {player} {json.dumps(msg, ensure_ascii=False)}")
        except Exception as e:
            log("RCON-Fehler", e)


# ---------- Aufgaben ----------
def tasks_cmd(req, args):
    tasks = read_json(TASKS, [])
    sub = (args[0].lower() if args else "list")
    if sub in ("add", "neu", "+") and len(args) > 1:
        text = " ".join(args[1:])[:300]
        nr = max([t["nr"] for t in tasks] or [0]) + 1
        tasks.append({"nr": nr, "text": text, "von": req["player"], "erstellt": int(time.time()), "erledigt": None, "quelle": "ingame"})
        write_json(TASKS, tasks)
        say(req["player"], f"Aufgabe #{nr} gespeichert: {text}", "green")
    elif sub in ("done", "fertig", "erledigt") and len(args) > 1 and args[1].lstrip("#").isdigit():
        nr = int(args[1].lstrip("#"))
        t = next((t for t in tasks if t["nr"] == nr and not t["erledigt"]), None)
        if t:
            t["erledigt"] = int(time.time())
            write_json(TASKS, tasks)
            say(req["player"], f"Aufgabe #{nr} abgehakt.", "green")
        else:
            say(req["player"], f"Keine offene Aufgabe #{nr}.", "red")
    else:
        open_ = [t for t in tasks if not t["erledigt"]]
        if not open_:
            say(req["player"], "Keine offenen Aufgaben.", "gray")
        for t in open_[-10:]:
            say(req["player"], f"#{t['nr']} {t['text']}", "white")


# ---------- Status ----------
def status_text():
    live, st = read_json(os.path.join(DASH, "live.json"), {}), read_json(os.path.join(DASH, "status.json"), {})
    tps = (live.get("tps") or {}).get("tps")
    pl = live.get("players") or {}
    sysd = live.get("system") or {}
    ow = ((st.get("world") or {}).get("pregen") or {}).get("minecraft:overworld", {})
    b = (st.get("backups") or {}).get("cloud") or {}
    up = (b.get("last_upload") or {}).get("time")
    parts = [f"TPS {tps:.1f}" if tps is not None else "TPS –",
             f"{pl.get('online', 0)}/{pl.get('max', '–')} online ({', '.join(pl.get('names') or []) or 'niemand'})",
             f"CPU {sysd.get('cpu', '–')} %",
             f"RAM {sysd.get('ram_used', 0) / 2**30:.1f}/{sysd.get('ram_total', 0) / 2**30:.0f} GB" if sysd.get("ram_total") else "",
             f"Pack {(st.get('pack') or {}).get('version', '–')}",
             f"Oberwelt-Pregen {ow.get('percent', 0):.1f} % ({ow.get('state', '–')})" if ow else "",
             f"letztes Backup {time.strftime('%d.%m. %H:%M', time.localtime(up))}" if up else ""]
    return " · ".join(p for p in parts if p)


# ---------- Wächter (/claude waechter …, Knöpfe aus den Wächter-Meldungen von watch.py) ----------
WSTATE = os.path.join(STATE, "waechter.json")
WCTL = os.path.join(STATE, "waechter-steuerung.json")


def unit_running(pattern):
    r = subprocess.run(["systemctl", "list-units", pattern, "--no-legend", "--state=active,activating"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def waechter_cmd(req, args):
    sub = (args[0].lower() if args else "status")
    w = read_json(WSTATE, {})
    m = w.get("messung") or {}
    if sub == "status":
        say(req["player"], f"MSPT {m.get('mspt') or 0:.0f} · TPS {m.get('tps') or 0:.1f} · Chunks {m.get('chunks', '?')} · "
                           f"Entities {m.get('entities', '?')} · Block-Entities {m.get('block_entities', '?')} · Items {m.get('items', '?')} · "
                           f"RAM {m.get('ram', '?')} GB · Platte {m.get('disk', '?')} %", "aqua")
        for a in (w.get("aktiv") or [])[:4]:
            say(req["player"], f"Offen: {a.get('text')}", "yellow")
    elif sub in ("leer", "neustart-leer"):
        if unit_running("mc-*restart*.service"):
            say(req["player"], "Ein Neustart ist schon eingeplant.", "gray")
        else:
            subprocess.run(["systemd-run", f"--unit=mc-waechter-restart-empty-{int(time.time())}", "/usr/local/bin/mc-restart-when-empty"])
            say(req["player"], "Neustart eingeplant – sobald niemand mehr online ist.", "green")
    elif sub in ("abstimmung", "vote"):
        if unit_running("mc-*vote*.service"):
            say(req["player"], "Es läuft schon eine Abstimmung.", "gray")
        else:
            os.makedirs(os.path.join(MC, "restart-vote"), exist_ok=True)
            with open(os.path.join(MC, "restart-vote", "info.txt"), "w", encoding="utf-8") as f:
                f.write("Kein Update – nur ein Neustart gegen den Lag (gibt hängende Chunks frei)\n")
            subprocess.run(["systemd-run", f"--unit=mc-waechter-vote-{int(time.time())}",
                            "--setenv=VOTE_VERSION=Neustart", "--setenv=VOTE_CLIENT=false", "/usr/local/bin/mc-restart-vote", "3"])
            say(req["player"], "Neustart-Abstimmung gestartet.", "green")
    elif sub in ("stumm", "ruhe") :
        mins = int(args[1]) if len(args) > 1 and args[1].isdigit() else 60
        mins = max(5, min(mins, 24 * 60))
        write_json(WCTL, {"stumm_bis": int(time.time()) + mins * 60})
        say(req["player"], f"Wächter-Meldungen {mins} Min. stumm (kritische kommen trotzdem).", "gray")
    elif sub in ("laut", "an"):
        write_json(WCTL, {"stumm_bis": 0})
        say(req["player"], "Wächter-Meldungen wieder an.", "gray")
    else:
        say(req["player"], "/claude waechter status · leer · abstimmung · stumm <Min.> · laut", "gray")


# ---------- Claude ----------
def token_env():
    env = {}
    try:
        for line in open(TOKEN_FILE, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return env if env.get("CLAUDE_CODE_OAUTH_TOKEN") else None


def say_actions(player, acts):
    parts = [{"text": "[Claude] ", "color": "light_purple"}, {"text": "Vorschlag:", "color": "gray"}]
    for a in acts[:4]:
        w = a.split()
        key = w[0].lower() if w else ""
        if key not in ACTIONS:
            continue
        label, hover = ACTIONS[key]
        cmd = "/claude waechter " + " ".join(w[:2])
        if key == "stumm" and len(w) > 1:
            label = f"Stumm {w[1]} Min."
        parts.append({"text": f" [{label}]", "color": "aqua", "bold": True,
                      "clickEvent": {"action": "run_command", "value": cmd}, "hoverEvent": {"action": "show_text", "contents": hover}})
    if len(parts) > 2:
        rcon(f"tellraw {player} {json.dumps(parts, ensure_ascii=False)}")


def run_claude(prompt, session):
    tok = token_env()
    env = {"HOME": "/var/lib/claudebot", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **tok}
    cmd = AS_BOT + [CLAUDE, "-p", "--model", MODEL, "--output-format", "json", f"--tools={TOOLS}",
                    f"--allowedTools={TOOLS}", "--append-system-prompt", SYSTEM] + [f"--add-dir={d}" for d in READ_DIRS]
    if session:
        cmd += ["--resume", session]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, env=env, cwd=PROJECT)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        d = {}
    return r.returncode, d, r.stderr


def ask_claude(req):
    tok = token_env()
    if not tok:
        say(req["player"], "Ich bin noch nicht angemeldet. Stefan: auf dem Server `claude setup-token` ausführen und den Token in /etc/mc-claude/token.env eintragen.", "red")
        return
    sessions = read_json(SESSIONS, {})
    sess = sessions.get(req["player"])
    prompt = (f"[{time.strftime('%d.%m. %H:%M')}] {req['player']} (in {req.get('dim')} bei "
              f"{' '.join(str(x) for x in req.get('pos') or [])}) schreibt: {req['text']}")
    t0 = time.time()
    try:
        rc, d, err = run_claude(prompt, sess)
        if sess and (rc != 0 or d.get("is_error")):   # Sitzung weg/kaputt → neuen Chat beginnen
            log("Sitzung nicht fortsetzbar, neuer Chat", (err or "")[-200:].replace("\n", " "))
            sess = None
            rc, d, err = run_claude("(Neuer Chat – der alte ließ sich nicht fortsetzen.)\n" + prompt, None)
    except subprocess.TimeoutExpired:
        say(req["player"], f"Keine Antwort nach {TIMEOUT} s, bitte nochmal fragen.", "red")
        return
    answer = (d.get("result") or "").strip()
    if rc != 0 or not answer:
        log("Claude-Fehler", rc, (err or "")[-400:].replace("\n", " "))
        say(req["player"], "Claude hat gerade nicht geantwortet (Limit oder Anmeldung?). Später nochmal versuchen.", "red")
        return
    if d.get("session_id"):
        sessions[req["player"]] = d["session_id"]
        write_json(SESSIONS, sessions)
    lines = [l.strip() for l in answer.splitlines() if l.strip()]
    tag = lambda l, t: l.upper().startswith(t)
    new_tasks = [l.split(":", 1)[1].strip() for l in lines if tag(l, "AUFGABE:")]
    acts = [l.split(":", 1)[1].strip() for l in lines if tag(l, "AKTION:")]
    text = " ".join(l for l in lines if not tag(l, "AUFGABE:") and not tag(l, "AKTION:"))
    say(req["player"], text)
    for nt in new_tasks:
        tasks_cmd(req, ["add", nt])
    if acts:
        say_actions(req["player"], acts)
    h = read_json(HIST, [])
    write_json(HIST, (h + [{"player": req["player"], "q": req["text"], "a": text, "t": int(time.time())}])[-200:])
    log(f"Frage von {req['player']} beantwortet in {time.time() - t0:.1f} s (Sitzung {'fortgesetzt' if sess else 'neu'})")


def handle(req):
    text = (req.get("text") or "").strip()
    args = text.split()
    head = args[0].lower() if args else ""
    if head in ("aufgabe", "aufgaben", "task", "tasks"):
        tasks_cmd(req, args[1:])
    elif head in ("neu", "reset", "new") and len(args) == 1:
        sessions = read_json(SESSIONS, {})
        sessions.pop(req["player"], None)
        write_json(SESSIONS, sessions)
        say(req["player"], "Neuer Chat – ich habe das bisherige Gespräch vergessen.", "gray")
    elif head in ("waechter", "wächter", "watch"):
        waechter_cmd(req, args[1:])
    elif head == "status" and len(args) == 1:
        say(req["player"], status_text(), "aqua")
    elif head in ("hilfe", "help", "?") and len(args) == 1:
        say(req["player"], "/claude <Frage> (fortlaufender Chat) · /claude neu · /claude status · /claude waechter · /claude aufgabe add|list|done", "gray")
    elif text:
        ask_claude(req)


def main():
    os.makedirs(STATE, exist_ok=True)
    os.makedirs(INBOX, exist_ok=True)
    log("Brücke gestartet")
    while True:
        for f in sorted(glob.glob(os.path.join(INBOX, "*.json"))):
            req = read_json(f, None)
            try:
                os.remove(f)
            except OSError:
                pass
            if not req or not re.fullmatch(r"[A-Za-z0-9_]{3,16}", str(req.get("player", ""))):
                continue
            if str(req.get("uuid", "")) not in ALLOWED_UUIDS:   # Claude nur für Stefan (zusätzlich zur Sperre im KubeJS-Befehl)
                log("Anfrage abgelehnt (nicht freigegeben)", req.get("player"))
                continue
            try:
                handle(req)
            except Exception as e:
                log("Fehler", type(e).__name__, e)
                say(req["player"], "Da ist etwas schiefgelaufen, Details stehen im Brücken-Log.", "red")
        time.sleep(1)


if __name__ == "__main__":
    main()
