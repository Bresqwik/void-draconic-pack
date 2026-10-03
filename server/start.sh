#!/usr/bin/env bash
# Void & Draconic Server: holt vor jedem Start die neueste Pack-Version und startet dann NeoForge.
cd "$(dirname "$0")"
PACK=https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/pack.toml
BOOT=https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar
if [ ! -f run.sh ]; then
  echo "NeoForge ist noch nicht installiert. Bitte zuerst ./install.sh ausfuehren."
  exit 1
fi
[ -f packwiz-installer-bootstrap.jar ] || curl -fL -o packwiz-installer-bootstrap.jar "$BOOT"
java -jar packwiz-installer-bootstrap.jar -g -s server "$PACK" || echo "Pack-Update fehlgeschlagen, starte mit den vorhandenen Mods."
./run.sh nogui
