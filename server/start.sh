#!/usr/bin/env bash
# Void & Draconic Server (Minecraft 1.20.1 / Forge): holt vor jedem Start die neueste Pack-Version und startet dann Forge.
cd "$(dirname "$0")"
REPO=Bresqwik/void-draconic-pack
FORGE=1.20.1-47.4.26
ARGS=libraries/net/minecraftforge/forge/$FORGE/unix_args.txt
BOOT=https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar
# Forge 1.20.1 läuft mit Java 17 (Java 21 bleibt für andere Zwecke installiert)
JAVA=/usr/lib/jvm/temurin-17-jdk-amd64/bin/java
[ -x "$JAVA" ] || JAVA=java
if [ ! -f "$ARGS" ]; then
  echo "Forge $FORGE ist noch nicht installiert. Bitte zuerst setup-linux.sh ausfuehren."
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
"$JAVA" -jar packwiz-installer-bootstrap.jar -g -s server "$PACK" || echo "Pack-Update fehlgeschlagen, starte mit den vorhandenen Mods."
exec "$JAVA" @user_jvm_args.txt @"$ARGS" nogui
