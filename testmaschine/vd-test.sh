#!/bin/bash
# Void & Draconic – Test-Instanz starten (macOS)
# Holt den Pack-Stand eines Branches in die Test-Instanz und startet sie mit dem Test-Konto.
# Aufruf:  ./vd-test.sh [branch] [welt]      (Standard: test Sandbox; NOSYNC=1 überspringt den Sync)
set -euo pipefail
BRANCH="${1:-test}"
WORLD="${2:-Sandbox}"
ACCOUNT="${ACCOUNT:-MarkMero}"
PRISM="/Applications/Prism Launcher.app/Contents/MacOS/prismlauncher"
INST="$HOME/Library/Application Support/PrismLauncher/instances/Void-Draconic-Test"
MC="$INST/minecraft"
[ -d "$INST" ] || { echo "Test-Instanz fehlt: $INST (siehe README.md)"; exit 1; }
if pgrep -f "instances/Void-Draconic-Test" >/dev/null; then echo "Test-Instanz läuft schon."; exit 1; fi

if [ -z "${NOSYNC:-}" ]; then
  JAVA="$(grep '^JavaPath=' "$INST/instance.cfg" | cut -d= -f2-)"
  [ -n "$JAVA" ] || JAVA="java"
  URL="https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/$BRANCH/pack.toml"
  echo "Sync: $URL"
  (cd "$MC" && "$JAVA" -jar packwiz-installer-bootstrap.jar -g "$URL")
fi

echo "Starte Test-Instanz als $ACCOUNT, Welt $WORLD"
nohup "$PRISM" --launch Void-Draconic-Test --profile "$ACCOUNT" --world "$WORLD" >/dev/null 2>&1 &
