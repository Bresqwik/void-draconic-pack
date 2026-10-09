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
TIMEOUT = 120

SYSTEM = """Du bist Claude, der Assistent im Minecraft-Server „Void & Draconic“ (Modpack für Minecraft 1.20.1 mit Forge,
Tech im Valhelsia-Stil: Mekanism, Refined Storage, Draconic Evolution, Create, Botania, Twilight Forest, The Abyss II u. v. m.).
Ein Spieler fragt dich direkt aus dem Spiel-Chat. Antworte auf Deutsch, kurz und praktisch: höchstens 4 Sätze, keine
Markdown-Formatierung, keine Aufzählungszeichen, keine Überschriften. Du hast keine Werkzeuge und kannst nichts am Server
ändern; sag ehrlich, wenn du etwas nicht sicher weißt. Will der Spieler, dass du dir etwas merkst oder später erledigst,
hänge ans Ende eine eigene Zeile „AUFGABE: <kurzer Text>“ an; die wird in die Aufgabenliste übernommen, die Stefans
Claude-Code-Sitzung später abarbeitet."""


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


def ask_claude(req):
    tok = token_env()
    if not tok:
        say(req["player"], "Ich bin noch nicht angemeldet. Stefan: auf dem Server `claude setup-token` ausführen und den Token in /etc/mc-claude/token.env eintragen.", "red")
        return
    hist = [h for h in read_json(HIST, []) if h.get("player") == req["player"]][-6:]
    tasks = [t for t in read_json(TASKS, []) if not t["erledigt"]][-15:]
    ctx = [f"Serverstatus: {status_text()}",
           f"Spieler: {req['player']} in {req.get('dim')} bei {' '.join(str(x) for x in req.get('pos') or [])}",
           "Offene Aufgaben: " + ("; ".join(f"#{t['nr']} {t['text']}" for t in tasks) or "keine")]
    if hist:
        ctx.append("Bisheriges Gespräch:\n" + "\n".join(f"Spieler: {h['q']}\nClaude: {h['a']}" for h in hist))
    prompt = "\n".join(ctx) + f"\n\nNeue Frage von {req['player']}: {req['text']}"
    env = {"HOME": "/var/lib/claudebot", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **tok}
    t0 = time.time()
    try:
        r = subprocess.run(AS_BOT + [CLAUDE, "-p", "--tools", "", "--no-session-persistence", "--model", MODEL,
                                     "--system-prompt", SYSTEM, "--output-format", "text"],
                           input=prompt, capture_output=True, text=True, timeout=TIMEOUT, env=env, cwd="/var/lib/claudebot")
        answer = r.stdout.strip()
        if r.returncode != 0 or not answer:
            log("Claude-Fehler", r.returncode, (r.stderr or "")[-400:].replace("\n", " "))
            say(req["player"], "Claude hat gerade nicht geantwortet (Limit oder Anmeldung?). Später nochmal versuchen.", "red")
            return
    except subprocess.TimeoutExpired:
        say(req["player"], f"Keine Antwort nach {TIMEOUT} s, bitte nochmal fragen.", "red")
        return
    lines = [l for l in answer.splitlines() if l.strip()]
    new_tasks = [l.split(":", 1)[1].strip() for l in lines if l.strip().upper().startswith("AUFGABE:")]
    text = " ".join(l.strip() for l in lines if not l.strip().upper().startswith("AUFGABE:"))
    say(req["player"], text)
    for nt in new_tasks:
        tasks_cmd(req, ["add", nt])
    h = read_json(HIST, [])
    write_json(HIST, (h + [{"player": req["player"], "q": req["text"], "a": text, "t": int(time.time())}])[-60:])
    log(f"Frage von {req['player']} beantwortet in {time.time() - t0:.1f} s")


def handle(req):
    text = (req.get("text") or "").strip()
    args = text.split()
    head = args[0].lower() if args else ""
    if head in ("aufgabe", "aufgaben", "task", "tasks"):
        tasks_cmd(req, args[1:])
    elif head == "status" and len(args) == 1:
        say(req["player"], status_text(), "aqua")
    elif head in ("hilfe", "help", "?") and len(args) == 1:
        say(req["player"], "/claude <Frage> · /claude status · /claude aufgabe add <Text> · /claude aufgabe list · /claude aufgabe done <Nr>", "gray")
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
            try:
                handle(req)
            except Exception as e:
                log("Fehler", type(e).__name__, e)
                say(req["player"], "Da ist etwas schiefgelaufen, Details stehen im Brücken-Log.", "red")
        time.sleep(1)


if __name__ == "__main__":
    main()
