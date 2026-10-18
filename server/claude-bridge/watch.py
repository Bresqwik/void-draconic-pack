#!/usr/bin/env python3
"""Void & Draconic – Server-Wächter (Dauerdienst mc-claude-watch.service), läuft unabhängig von Stefans PC/Mac.

Jede Minute: TPS/MSPT (Dashboard live.json), Chunks/Entities/Block-Entities (ServerCore /statistics), Boden-Items,
RAM/Platte, Spieler. Erkennt Lag, hängende Chunks, Item-Fluten, einen hängenden Server und volle Platte.

Selbst erledigt (von Stefan freigegeben, 18.10.2026):
  - hängender Server (Prozess läuft, Log steht, RCON tot)  → Neustart
  - mehr als ITEMS_MAX Boden-Items                          → Items > 128 Blöcke von jedem Spieler entfernen
  - Lag ohne Spieler über längere Zeit                      → Neustart, sobald leer (mc-restart-when-empty)
Alles andere: Meldung privat an Stefan (nur wenn online), mit kurzer Diagnose von Claude (ohne Werkzeuge) und
anklickbaren Vorschlägen (/claude waechter …, ausgeführt von der Brücke bridge.py). Zusätzlich
/var/lib/mc-claude/waechter.json für die Admin-Karte (Dashboard /api/admin/waechter, nur Admins) im Dashboard.
Nur Python-Standardbibliothek. Teilt RCON, Token und claudebot-Aufruf mit bridge.py.
"""
import json, os, re, shutil, subprocess, threading, time
import bridge  # rcon(), token_env(), log-Pfade, CLAUDE/AS_BOT

MC = "/opt/void-draconic"
DASH = "/var/www/mc-dashboard/data"
STATE = "/var/lib/mc-claude"
OUT = os.path.join(STATE, "waechter.json")   # nur root, claudebot und das Dashboard-Login (Gruppe mcclaude)
METRICS = os.path.join(STATE, "waechter-messwerte.log")
WLOG = os.path.join(STATE, "waechter.log")
NOTIFY = ["stman476"]          # bekommt die privaten Meldungen (nur wenn online)
ITEMS_MAX = 3000               # ab hier ferne Items automatisch entfernen
MSPT_WARN, MSPT_CRIT = 50, 70  # ab 50 ms fällt die TPS unter 20
LAG_MINUTES = 3                # so lange muss der Lag anhalten, bevor gemeldet wird
EMPTY_LAG_MINUTES = 20         # Lag ohne Spieler so lange → Neustart, sobald leer
CHUNKS_WARN, BE_WARN = 2500, 120000
COOLDOWN = 30 * 60             # gleiche Meldung höchstens alle 30 Min.
HANG_CHECKS = 5                # so viele Minuten RCON tot + Log steht → hängt


def wlog(*a):
    with open(WLOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a) + "\n")


def rcon(cmd):
    try:
        return bridge.rcon(cmd)
    except Exception:
        return None


def tell(player, parts):
    """parts: Liste von (Text, Farbe) oder dicts (mit clickEvent)."""
    msg = [{"text": "[Wächter] ", "color": "gold"}]
    for p in parts:
        msg.append(p if isinstance(p, dict) else {"text": p[0], "color": p[1]})
    rcon(f"tellraw {player} {json.dumps(msg, ensure_ascii=False)}")


def button(label, cmd, hover):
    return {"text": f" [{label}]", "color": "aqua", "bold": True,
            "clickEvent": {"action": "run_command", "value": cmd},
            "hoverEvent": {"action": "show_text", "contents": hover}}


def unit_running(pattern):
    r = subprocess.run(["systemctl", "list-units", pattern, "--no-legend", "--state=active,activating"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def server_active():
    return subprocess.run(["systemctl", "is-active", "--quiet", "void-draconic"]).returncode == 0


def active_seconds():
    """Wie lange der Minecraft-Dienst schon läuft (Sekunden), 0 wenn nicht aktiv."""
    r = subprocess.run(["systemctl", "show", "void-draconic", "-p", "ActiveEnterTimestampMonotonic"],
                       capture_output=True, text=True)
    try:
        t = int(r.stdout.strip().split("=", 1)[1]) / 1e6
        return time.monotonic() - t if t else 0
    except (IndexError, ValueError):
        return 0


def planned_restart():
    """Läuft gerade ein geplanter Neustart/Stopp oder eine Abstimmung?"""
    return unit_running("mc-*restart*.service") or unit_running("mc-*vote*.service")


class Watch:
    def __init__(self):
        self.state = bridge.read_json(OUT, {}) or {}
        self.alerts = self.state.get("alerts", [])     # Verlauf für das Dashboard
        self.active = {}                               # Typ -> {seit, text}
        self.last_sent = {}                            # Typ -> Zeit
        self.lag_min = 0
        self.empty_lag_min = 0
        self.rcon_dead = 0
        self.empty_restart_at = 0
        self.mute_until = 0

    # ---------- Messen ----------
    def measure(self):
        live = bridge.read_json(os.path.join(DASH, "live.json"), {})
        tps = live.get("tps") or {}
        m = {"t": int(time.time()), "online": bool(live.get("online")),
             "players": (live.get("players") or {}).get("names") or [],
             "tps": tps.get("tps"), "mspt": tps.get("mspt"),
             "dims": {k.split(":")[-1]: round(v.get("mspt") or 0, 1) for k, v in (tps.get("dims") or {}).items()
                      if (v.get("mspt") or 0) >= 1},
             "ram": round(((live.get("system") or {}).get("ram_used") or 0) / 2**30, 1)}
        du = shutil.disk_usage("/")
        m["disk"] = round(100 * du.used / du.total)
        st = rcon("statistics")
        m["rcon"] = st is not None
        if st:
            for key, name in (("chunks", r"chunk count: ([\d.,]+)"), ("entities", r"entity count: ([\d.,]+)"),
                              ("block_entities", r"block entity count: ([\d.,]+)")):
                x = re.search(name, st, re.I)
                if x:
                    m[key] = int(re.sub(r"[.,]", "", x.group(1)))
            it = rcon("execute if entity @e[type=minecraft:item]")
            x = re.search(r"count: (\d+)", it or "")
            m["items"] = int(x.group(1)) if x else 0
        try:
            m["log_age"] = int(time.time() - os.path.getmtime(os.path.join(MC, "logs", "latest.log")))
        except OSError:
            m["log_age"] = None
        return m

    # ---------- Melden ----------
    def notify(self, kind, level, text, actions=(), diagnose=None, force=False):
        now = time.time()
        first = kind not in self.active
        self.active.setdefault(kind, {"seit": int(now), "text": text, "level": level})
        self.active[kind].update(text=text, level=level)
        if not force and now - self.last_sent.get(kind, 0) < COOLDOWN:
            return
        self.last_sent[kind] = now
        entry = {"t": int(now), "typ": kind, "stufe": level, "text": text}
        self.alerts = (self.alerts + [entry])[-80:]
        wlog(level.upper(), kind, text)
        self.save()
        if now < self.mute_until and level != "krit":
            return

        def send(diag):
            if diag:
                entry["diagnose"] = diag
                self.save()
            for p in NOTIFY:
                if p not in self.players:
                    continue
                color = {"info": "green", "warn": "yellow", "krit": "red"}.get(level, "white")
                tell(p, [(text, color)])
                if diag:
                    tell(p, [("Claude: ", "light_purple"), (diag, "gray")])
                if actions:
                    tell(p, [("Möglich:", "gray")] + [button(a, c, h) for a, c, h in actions])
        if diagnose and first:
            threading.Thread(target=lambda: send(self.ask_claude(diagnose)), daemon=True).start()
        else:
            send(None)

    def resolve(self, kind, text):
        if kind in self.active:
            del self.active[kind]
            self.last_sent.pop(kind, None)
            self.alerts = (self.alerts + [{"t": int(time.time()), "typ": kind, "stufe": "ok", "text": text}])[-80:]
            wlog("OK", kind, text)
            self.save()
            for p in NOTIFY:
                if p in self.players:
                    tell(p, [(text, "green")])

    def ask_claude(self, data):
        """Kurze Diagnose (2 Sätze) von Claude ohne Werkzeuge; None bei Fehler/Limit."""
        tok = bridge.token_env()
        if not tok:
            return None
        system = ("Du bist der Server-Wächter des Minecraft-Modpack-Servers „Void & Draconic“ (1.20.1 Forge, ~300 Mods: "
                  "Mekanism, Refined Storage, Create, Draconic Evolution, Just Dire Things, BetterEnd, C2ME, ServerCore). "
                  "Bekannte Ursachen: hängende Chunks nach weiten Flügen (Items altern nicht), Boden-Item-Fluten, "
                  "fallender Kies, große Maschinenparks (Block-Entities), viele Spieler gleichzeitig. Antworte auf Deutsch "
                  "in höchstens 2 kurzen Sätzen ohne Markdown: wahrscheinliche Ursache + empfohlene Maßnahme.")
        env = {"HOME": "/var/lib/claudebot", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **tok}
        try:
            r = subprocess.run(bridge.AS_BOT + [bridge.CLAUDE, "-p", "--tools", "", "--no-session-persistence",
                                                "--model", bridge.MODEL, "--system-prompt", system,
                                                "--output-format", "text"],
                               input=json.dumps(data, ensure_ascii=False), capture_output=True, text=True,
                               timeout=90, env=env, cwd="/var/lib/claudebot")
            out = " ".join(r.stdout.split()).strip()
            return out[:400] if r.returncode == 0 and out else None
        except Exception as e:
            wlog("Claude-Fehler", e)
            return None

    def save(self):
        data = {"zeit": int(time.time()), "aktiv": [{"typ": k, **v} for k, v in self.active.items()],
                "verlauf": self.alerts[-40:], "messung": getattr(self, "m", {}),
                "stumm_bis": int(self.mute_until)}
        try:
            bridge.write_json(OUT, data)
        except OSError as e:
            wlog("Dashboard-Datei", e)

    # ---------- Prüfen ----------
    def check(self):
        m = self.m = self.measure()
        self.players = m["players"]
        with open(METRICS, "a", encoding="utf-8") as f:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
        ctl = bridge.read_json(os.path.join(STATE, "waechter-steuerung.json"), {})
        self.mute_until = ctl.get("stumm_bis", 0)

        # 1) Hängender Server: Dienst aktiv, Log steht, RCON tot – nicht während geplanter Neustarts/Start
        if server_active() and not planned_restart():
            # Start dauert ~2 Min. (BCLib-Patches aus); nach 15 Min. Laufzeit muss RCON antworten
            if active_seconds() > 900 and not m["rcon"] and (m["log_age"] or 0) > 180:
                self.rcon_dead += 1
            else:
                self.rcon_dead = 0
            if self.rcon_dead >= HANG_CHECKS:
                wlog("KRIT Server hängt – Neustart")
                self.alerts.append({"t": int(time.time()), "typ": "haenger", "stufe": "krit",
                                    "text": "Server hing (keine Antwort, Log stand) – automatisch neu gestartet."})
                self.save()
                subprocess.run(["systemctl", "kill", "-s", "SIGKILL", "void-draconic"])
                time.sleep(5)
                subprocess.run(["systemctl", "restart", "void-draconic"])
                self.rcon_dead = 0
                return
        if not m["rcon"]:
            return

        # 2) Boden-Items
        if m.get("items", 0) > ITEMS_MAX:
            # @e ohne Positionsangabe erfasst alle Dimensionen; @a[distance=..] nur Spieler in derselben Dimension
            rcon("execute as @e[type=minecraft:item] at @s unless entity @a[distance=..128] run kill @s")
            x = re.search(r"count: (\d+)", rcon("execute if entity @e[type=minecraft:item]") or "")
            n = m["items"] - (int(x.group(1)) if x else m["items"])
            self.notify("items", "info", f"{m['items']} Items lagen am Boden – {n} weit entfernte (über 128 Blöcke von jedem Spieler) automatisch entfernt.",
                        force=True)
            self.active.pop("items", None)

        # 3) Lag
        mspt = m.get("mspt") or 0
        self.lag_min = self.lag_min + 1 if mspt >= MSPT_WARN else 0
        if self.lag_min >= LAG_MINUTES:
            lvl = "krit" if mspt >= MSPT_CRIT else "warn"
            top = ", ".join(f"{k} {v} ms" for k, v in sorted(m["dims"].items(), key=lambda x: -x[1])[:3])
            self.notify("lag", lvl, f"Lag: MSPT {mspt:.0f} (TPS {m.get('tps') or 0:.1f}) seit {self.lag_min} Min. – {top}. "
                                    f"Chunks {m.get('chunks', '?')}, Block-Entities {m.get('block_entities', '?')}, Items {m.get('items', '?')}.",
                        actions=[("Claude fragen", "/claude Der Wächter meldet Lag – was ist die Ursache und was soll ich tun? Schau in die Messwerte und das Log.", "Claude sieht sich Messwerte und Log an"),
                                 ("Status", "/claude waechter status", "Aktuelle Messwerte"),
                                 ("Neustart-Abstimmung", "/claude waechter abstimmung", "Alle Online-Spieler fragen"),
                                 ("Neustart wenn leer", "/claude waechter leer", "Neustart, sobald niemand online ist"),
                                 ("1 h stumm", "/claude waechter stumm 60", "Wächter-Meldungen 60 Min. aus")],
                        diagnose={"messung": m, "lag_minuten": self.lag_min})
        elif mspt < MSPT_WARN - 10 and "lag" in self.active:
            self.resolve("lag", f"Lag vorbei: MSPT {mspt:.0f}, TPS {m.get('tps') or 0:.1f}.")

        # 4) Lag ohne Spieler → Neustart, sobald leer (höchstens alle 6 h)
        self.empty_lag_min = self.empty_lag_min + 1 if (not m["players"] and mspt >= 35) else 0
        if self.empty_lag_min >= EMPTY_LAG_MINUTES and time.time() - self.empty_restart_at > 6 * 3600 and not planned_restart():
            self.empty_restart_at = time.time()
            subprocess.run(["systemd-run", "--unit=mc-waechter-restart-empty-%d" % int(time.time()),
                            "/usr/local/bin/mc-restart-when-empty"])
            self.alerts.append({"t": int(time.time()), "typ": "leer-lag", "stufe": "info",
                                "text": f"Ohne Spieler {self.empty_lag_min} Min. Lag (MSPT {mspt:.0f}) – Neustart, sobald leer, eingeplant."})
            wlog("Leer-Lag → Neustart eingeplant")
            self.save()

        # 5) Hängende Chunks / viele Block-Entities bei wenigen Spielern
        few = len(m["players"]) <= 2
        if few and (m.get("chunks", 0) > CHUNKS_WARN or m.get("block_entities", 0) > BE_WARN):
            self.notify("chunks", "warn", f"Viele geladene Chunks: {m.get('chunks')} Chunks, {m.get('block_entities')} Block-Entities "
                                          f"bei {len(m['players'])} Spieler(n) – vermutlich hängen Chunks nach Flügen.",
                        actions=[("Claude fragen", "/claude Der Wächter meldet viele geladene Chunks – woher kommen sie und was soll ich tun?", "Claude sieht sich Messwerte und Log an"),
                                 ("Neustart wenn leer", "/claude waechter leer", "Gibt die hängenden Chunks frei"),
                                 ("Neustart-Abstimmung", "/claude waechter abstimmung", "Alle Online-Spieler fragen")],
                        diagnose={"messung": m})
        elif "chunks" in self.active and m.get("chunks", 0) < CHUNKS_WARN * 0.8 and m.get("block_entities", 0) < BE_WARN * 0.8:
            self.resolve("chunks", f"Chunks wieder normal ({m.get('chunks')}).")

        # 6) Platte
        if m["disk"] >= 90:
            self.notify("platte", "krit", f"Festplatte zu {m['disk']} % voll.")
        elif "platte" in self.active and m["disk"] < 85:
            self.resolve("platte", f"Festplatte wieder bei {m['disk']} %.")
        self.save()


def main():
    os.makedirs(STATE, exist_ok=True)
    w = Watch()
    w.players = []
    wlog("Wächter gestartet")
    while True:
        t0 = time.time()
        try:
            w.check()
        except Exception as e:
            wlog("Fehler", type(e).__name__, e)
        time.sleep(max(5, 60 - (time.time() - t0)))


if __name__ == "__main__":
    main()
