#!/usr/bin/env bash
# Void & Draconic Server: holt vor jedem Start die neueste Pack-Version und startet dann NeoForge.
cd "$(dirname "$0")"
REPO=Bresqwik/void-draconic-pack
BOOT=https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar
if [ ! -f run.sh ]; then
  echo "NeoForge ist noch nicht installiert. Bitte zuerst ./install.sh ausfuehren."
  exit 1
fi
[ -f packwiz-installer-bootstrap.jar ] || curl -fL -o packwiz-installer-bootstrap.jar "$BOOT"
# Über den genauen Commit laden: raw.githubusercontent.com hält "main" einige Minuten im Cache,
# dann würde nach einem Push noch die alte Version installiert. Ein Commit-Pfad ist nie veraltet.
SHA=$(curl -fsS -m 10 -H "Accept: application/vnd.github.sha" "https://api.github.com/repos/$REPO/commits/main" 2>/dev/null)
if [[ $SHA =~ ^[0-9a-f]{40}$ ]]; then
  PACK="https://raw.githubusercontent.com/$REPO/$SHA/pack.toml"
else
  PACK="https://raw.githubusercontent.com/$REPO/main/pack.toml"
fi
echo "Pack: $PACK"
java -jar packwiz-installer-bootstrap.jar -g -s server "$PACK" || echo "Pack-Update fehlgeschlagen, starte mit den vorhandenen Mods."
./run.sh nogui
