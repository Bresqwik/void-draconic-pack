#!/bin/bash
# Void & Draconic – Test-Instanz auf dem Mac einrichten (einmalig).
# Legt in Prism die Instanz „Void-Draconic-Test“ an (MC 1.20.1, Forge 47.4.26). Prism lädt Java selbst,
# und vor jedem Start holt packwiz den Pack-Stand vom Branch (Standard: test).
# Aufruf:  bash setup-mac.sh [branch]      danach Prism einmal neu starten (oder Instanzen neu laden)
set -euo pipefail
BRANCH="${1:-test}"
PRISM_DIR="$HOME/Library/Application Support/PrismLauncher"
INST="$PRISM_DIR/instances/Void-Draconic-Test"
BOOT="https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar"
RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
MAXMEM=$(( RAM_GB >= 24 ? 10240 : RAM_GB >= 16 ? 7168 : 5120 ))

[ -d "/Applications/Prism Launcher.app" ] || { echo "Prism Launcher fehlt in /Applications – bitte zuerst installieren."; exit 1; }
[ -d "$PRISM_DIR" ] || { echo "Prism einmal starten (legt $PRISM_DIR an), dann erneut ausführen."; exit 1; }
if [ -d "$INST" ]; then echo "Instanz gibt es schon: $INST"; else
  mkdir -p "$INST/minecraft"
  cat > "$INST/mmc-pack.json" <<'EOF'
{
    "components": [
        { "uid": "org.lwjgl3", "version": "3.3.1", "dependencyOnly": true },
        { "uid": "net.minecraft", "version": "1.20.1", "important": true },
        { "uid": "net.minecraftforge", "version": "47.4.26" }
    ],
    "formatVersion": 1
}
EOF
  cat > "$INST/instance.cfg" <<EOF
[General]
ConfigVersion=1.3
InstanceType=OneSix
name=Void & Draconic TEST (MarkMero)
OverrideMemory=true
MinMemAlloc=2048
MaxMemAlloc=$MAXMEM
AutomaticJava=true
AutomaticJavaSwitch=true
AutomaticJavaDownload=true
OverrideCommands=true
PreLaunchCommand=\"\$INST_JAVA\" -jar packwiz-installer-bootstrap.jar -g https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/$BRANCH/pack.toml
notes=Testinstanz: holt vor jedem Start den Branch $BRANCH. Nur mit dem Konto MarkMero spielen.
EOF
  curl -fsSL -o "$INST/minecraft/packwiz-installer-bootstrap.jar" "$BOOT"
  echo "Instanz angelegt: $INST (RAM max ${MAXMEM} MB, Branch $BRANCH)"
fi
echo "Nächste Schritte: Prism neu starten → MarkMero als Konto anmelden (Stefan selbst) → Instanz starten."
echo "Beim ersten Start lädt packwiz alle Mods (dauert). Dann im Spiel eine Kreativwelt „Sandbox“ (Cheats an) anlegen."
echo "Später starten mit:  \"/Applications/Prism Launcher.app/Contents/MacOS/prismlauncher\" --launch Void-Draconic-Test --profile MarkMero --world Sandbox"
