"""Test-Hub für das Dashboard (/admin/testhub/, nur Admins): Live-Stand und Verlauf der Testmaschinen.

Die Testmaschinen (MacBook, Windows-PC) schicken per POST mit eigenem Token. Auf dem Server liegt nur der SHA-256 des
Tokens (testhub/tokens.json: {"<sha256>": "mac" | "windows"}); daraus ergibt sich das Gerät.

  POST /api/testhub/push      JSON: feste Felder (status, phase, phases, progress, render, counts, …) ersetzen,
                              "log" ersetzt / "log_append" hängt an, "errors_append" hängt Funde an,
                              "reset": true beginnt einen neuen Lauf, "heartbeat": true + "device_state" nur Gerätestatus
  POST /api/testhub/bericht   vollständiger Bericht (JSON) zum aktuellen Lauf des Geräts
  GET  /api/testhub           Geräte mit aktuellem Lauf (ohne Fundliste) + Verlauf
  GET  /api/testhub/run?id=<id>               ein Lauf (für den Verlauf)
  GET  /api/testhub/errors?run=<id>&from=<n>   Funde eines Laufs ab Nummer n (für die Liste, nachladend)
  GET  /api/testhub/bericht?run=<id>           gespeicherter Bericht
Alte Adressen /api/rezepttest/push und /api/rezepttest/bericht (Test-Mod vd-rezepttest) landen hier als Gerät des Tokens.
"""
import hashlib, hmac, json, os, threading, time

DEVICES = {"mac": "MacBook", "windows": "Windows-PC"}
KEYS = {"status", "phase", "phases", "progress", "render", "counts", "byMod", "byCategory", "note", "summary", "title",
        "kind", "started", "finished", "branch", "commit", "detail", "links"}
MAX_LOG, MAX_ERRORS, MAX_ERR_PUSH, HISTORY = 600, 20000, 1000, 50
LOCK = threading.Lock()
BASE = ""


def _p(*a):
    return os.path.join(BASE, *a)


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def init(state):
    """Ordner anlegen und den alten Rezept-Test-Stand (rezepttest.json + Token-Hash) einmalig übernehmen."""
    global BASE
    BASE = os.path.join(state, "testhub")
    os.makedirs(_p("runs"), exist_ok=True)
    old_hash = os.path.join(state, "rezepttest.token.sha256")
    if not os.path.exists(_p("tokens.json")) and os.path.exists(old_hash):
        h = open(old_hash).read().strip().lower()
        if h:
            _save(_p("tokens.json"), {h: "mac"})
    old = os.path.join(state, "rezepttest.json")
    live = _load(_p("live.json"), {})
    if os.path.exists(old) and "mac" not in live:
        d = _load(old, {})
        errors = d.pop("errors", []) or []
        rid = _new_id("mac", d.get("started"))
        d.update({"id": rid, "device": "mac", "kind": "rezepttest", "title": d.get("title") or "Rezept-Test (EMI)",
                  "errors_count": len(errors), "errors_total": d.get("errors_total", len(errors))})
        if d.pop("bericht", None) and os.path.exists(os.path.join(state, "rezepttest-bericht.json")):
            os.replace(os.path.join(state, "rezepttest-bericht.json"), _p("runs", rid + ".bericht.json"))
            d["bericht"] = True
        _save(_p("runs", rid + ".json"), d)
        _save(_p("runs", rid + ".errors.json"), errors)
        live["mac"] = rid
        _save(_p("live.json"), live)
        os.replace(old, old + ".uebernommen")


def _new_id(device, started=None):
    t = time.strftime("%Y%m%d-%H%M%S", time.localtime(started or time.time()))
    rid = f"{t}-{device}"
    n = 2
    while os.path.exists(_p("runs", rid + ".json")):
        rid = f"{t}-{device}-{n}"
        n += 1
    return rid


def device_for(auth_header):
    """Gerät zum Bearer-Token oder None."""
    tok = (auth_header or "").removeprefix("Bearer ").strip()
    if len(tok) < 32:
        return None
    h = hashlib.sha256(tok.encode()).hexdigest()
    for want, dev in _load(_p("tokens.json"), {}).items():
        if hmac.compare_digest(h, want.lower()):
            return dev
    return None


def push(device, body, default_kind="test"):
    now = time.time()
    with LOCK:
        devs = _load(_p("devices.json"), {})
        dv = devs.setdefault(device, {})
        dv["seen"] = now
        if "device_state" in body:
            dv["state"] = str(body["device_state"])[:200]
        _save(_p("devices.json"), devs)
        if body.get("heartbeat") and not any(k in body for k in KEYS | {"reset", "log_append", "errors_append", "log"}):
            return None
        live = _load(_p("live.json"), {})
        rid = live.get(device)
        run = _load(_p("runs", rid + ".json"), None) if rid else None
        if body.get("reset") or run is None:
            rid = _new_id(device)
            run = {"id": rid, "device": device, "kind": default_kind, "created": now, "errors_count": 0, "errors_total": 0}
            _save(_p("runs", rid + ".errors.json"), [])
            live[device] = rid
            _save(_p("live.json"), live)
        for k in KEYS:
            if k in body:
                run[k] = body[k]
        if isinstance(body.get("log"), list):
            run["log"] = [str(x)[:600] for x in body["log"]][-MAX_LOG:]
        if isinstance(body.get("log_append"), list):
            run["log"] = ((run.get("log") or []) + [str(x)[:600] for x in body["log_append"]])[-MAX_LOG:]
        add = body.get("errors_append")
        if isinstance(add, list) and add:
            add = [e for e in add if isinstance(e, dict)][:MAX_ERR_PUSH]
            errs = _load(_p("runs", rid + ".errors.json"), [])
            room = max(0, MAX_ERRORS - len(errs))
            errs.extend(add[:room])
            _save(_p("runs", rid + ".errors.json"), errs)
            run["errors_count"] = len(errs)
            run["errors_total"] = run.get("errors_total", 0) + len(add)
        run.setdefault("started", now)
        run["updated"] = now
        if run.get("status") in ("fertig", "abgebrochen", "fehler") and not run.get("finished"):
            run["finished"] = now
        _save(_p("runs", rid + ".json"), run)
        return rid


def save_bericht(device, data):
    with LOCK:
        rid = _load(_p("live.json"), {}).get(device)
        if not rid:
            return None
        with open(_p("runs", rid + ".bericht.json"), "wb") as f:
            f.write(data)
        run = _load(_p("runs", rid + ".json"), {})
        run["bericht"] = True
        _save(_p("runs", rid + ".json"), run)
        return rid


def overview():
    live = _load(_p("live.json"), {})
    devs = _load(_p("devices.json"), {})
    out = {"now": time.time(), "devices": {}, "history": []}
    for dev, name in DEVICES.items():
        rid = live.get(dev)
        run = _load(_p("runs", rid + ".json"), None) if rid else None
        out["devices"][dev] = {"name": name, "seen": devs.get(dev, {}).get("seen"), "state": devs.get(dev, {}).get("state"),
                               "run": run, "has_token": dev in _load(_p("tokens.json"), {}).values()}
    runs = []
    for fn in os.listdir(_p("runs")):
        if fn.endswith(".json") and fn.count(".") == 1:
            r = _load(_p("runs", fn), None)
            if r:
                runs.append({k: r.get(k) for k in ("id", "device", "kind", "title", "status", "started", "finished",
                                                   "updated", "counts", "errors_total", "summary", "bericht", "branch", "commit")})
    runs.sort(key=lambda r: r.get("started") or 0, reverse=True)
    out["history"] = runs[:HISTORY]
    return out


def run(rid):
    if not rid or "/" in rid or ".." in rid:
        return None
    return _load(_p("runs", rid + ".json"), None)


def errors(rid, frm=0, limit=2000):
    if not rid or "/" in rid or ".." in rid:
        return {"errors": [], "total": 0}
    errs = _load(_p("runs", rid + ".errors.json"), [])
    frm = max(0, int(frm))
    return {"errors": errs[frm:frm + limit], "total": len(errs), "from": frm}


def bericht(rid):
    if not rid or "/" in rid or ".." in rid:
        return None
    try:
        with open(_p("runs", rid + ".bericht.json"), "rb") as f:
            return f.read()
    except OSError:
        return None
