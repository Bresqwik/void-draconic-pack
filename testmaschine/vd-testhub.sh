#!/usr/bin/env bash
# Meldungen der Testmaschine an den Test-Hub (Dashboard /admin/testhub/). Token liegt nur lokal in ~/.vd-testhub-token
# (oder ~/.vd-rezepttest-token), auf dem Server nur sein SHA-256 (testhub/tokens.json → Gerät).
#
#   vd-testhub.sh beat "bereit"                       Gerätezustand (ohne Lauf)
#   vd-testhub.sh start "Kombi-Test 0.6.34" [kind]    neuer Lauf (kind: test | rezepttest | performance …)
#   vd-testhub.sh log "Zeile 1" ["Zeile 2" …]         Zeilen ans Live-Log hängen
#   vd-testhub.sh step <key> <state> "Label" ["Detail"]   Phase setzen (state: todo | active | done | error)
#   vd-testhub.sh progress <done> <total> ["Prüfungen"]
#   vd-testhub.sh find <type> "Fundstelle" "Meldung"  Fund (type: fail | warn | crash | pass | …)
#   vd-testhub.sh end fertig|abgebrochen|fehler ["Zusammenfassung"]
#   vd-testhub.sh raw '{"…": …}'                      beliebiges JSON
set -euo pipefail
URL="${VD_TESTHUB_URL:-https://mc-void-draconic.bresqwik.org/api/testhub/push}"
TOKF="${VD_TESTHUB_TOKEN_FILE:-$HOME/.vd-testhub-token}"
[ -f "$TOKF" ] || TOKF="$HOME/.vd-rezepttest-token"
TOKEN="$(tr -d '\r\n' < "$TOKF")"
STATE="${TMPDIR:-/tmp}/vd-testhub-phases.json"

j() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
send() { curl -fsS -m 15 -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data-binary "$1" "$URL" >/dev/null; }

cmd="${1:-}"; shift || true
case "$cmd" in
  beat)     send "{\"heartbeat\":true,\"device_state\":$(j "${1:-bereit}")}" ;;
  start)    echo '[]' > "$STATE"
            send "{\"reset\":true,\"status\":\"läuft\",\"title\":$(j "$1"),\"kind\":$(j "${2:-test}"),\"log_append\":[$(j "$(date +%H:%M:%S) Start: $1")]}" ;;
  log)      lines=""; for l in "$@"; do lines="$lines,$(j "$(date +%H:%M:%S) $l")"; done; send "{\"log_append\":[${lines#,}]}" ;;
  step)     python3 - "$STATE" "$1" "$2" "${3:-$1}" "${4:-}" <<'EOF' > "$STATE.new" && mv "$STATE.new" "$STATE"
import json, sys
f, key, state, label, detail = sys.argv[1:6]
try: ph = json.load(open(f))
except Exception: ph = []
for p in ph:
    if p["key"] == key: p.update(state=state, label=label, **({"detail": detail} if detail else {})); break
else: ph.append({"key": key, "state": state, "label": label, **({"detail": detail} if detail else {})})
print(json.dumps(ph))
EOF
            send "{\"phase\":$(j "$1"),\"phases\":$(cat "$STATE")}" ;;
  progress) send "{\"progress\":{\"done\":$1,\"total\":$2,\"label\":$(j "${3:-Prüfungen}")}}" ;;
  find)     send "{\"errors_append\":[{\"type\":$(j "$1"),\"where\":$(j "$2"),\"msg\":$(j "$3")}],\"log_append\":[$(j "$(date +%H:%M:%S) [$1] $2: $3")]}" ;;
  end)      send "{\"status\":$(j "$1"),\"summary\":$(j "${2:-}"),\"log_append\":[$(j "$(date +%H:%M:%S) Ende: $1 ${2:-}")]}" ;;
  raw)      send "$1" ;;
  *)        sed -n '2,15p' "$0"; exit 1 ;;
esac
