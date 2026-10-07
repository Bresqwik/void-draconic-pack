#!/usr/bin/env bash
# Void & Draconic – Einrichtung auf einem frischen Linux-Server (Debian 12/13 oder Ubuntu 24.04), als root.
#
#   curl -fsSL https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/server/setup-linux.sh -o setup-linux.sh
#   ACCEPT_EULA=yes bash setup-linux.sh
#
# Einstellbar per Umgebungsvariable:
#   ACCEPT_EULA=yes        Minecraft-EULA (https://aka.ms/MinecraftEULA) akzeptieren. Ohne das startet der Server nicht.
#   RAM_GB=12              Arbeitsspeicher für Minecraft
#   PLAYERS="a b"          Spieler für Whitelist und OP
#   MC_DIR=/opt/void-draconic
#   SKIP_SYSTEMD=1         Kein Dienst einrichten (z. B. in Containern)
#   SKIP_FIREWALL=1        ufw nicht anfassen
set -euo pipefail

MC_DIR=${MC_DIR:-/opt/void-draconic}
MC_USER=minecraft
NEO=21.1.252
RAM_GB=${RAM_GB:-12}
PLAYERS=${PLAYERS:-"stman476 MarkMero"}
ACCEPT_EULA=${ACCEPT_EULA:-no}
PACK=https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/pack.toml
BOOT=https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar

step() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Bitte als root ausführen."; exit 1; }

step "Pakete"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl unzip jq tmux ca-certificates gnupg >/dev/null

step "Java 21 (Eclipse Temurin)"
if ! java -version 2>&1 | grep -q 'version "21'; then
  install -d -m 755 /etc/apt/keyrings
  curl -fsSL https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor --yes -o /etc/apt/keyrings/adoptium.gpg
  codename=$(. /etc/os-release; echo "$VERSION_CODENAME")
  echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $codename main" > /etc/apt/sources.list.d/adoptium.list
  apt-get update -qq
  apt-get install -y -qq temurin-21-jre >/dev/null
fi
java -version 2>&1 | head -1

step "Benutzer und Ordner"
id "$MC_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$MC_DIR" --shell /bin/bash "$MC_USER"
install -d -o "$MC_USER" -g "$MC_USER" "$MC_DIR"
cd "$MC_DIR"
as_mc() { su -s /bin/bash "$MC_USER" -c "cd '$MC_DIR' && $*"; }
# Downloads können sporadisch abbrechen: bis zu 3 Versuche
retry() { local n; for n in 1 2 3; do "$@" && return 0; echo "Versuch $n fehlgeschlagen, neuer Versuch in 10 s ..."; sleep 10; done; return 1; }

step "NeoForge $NEO"
if [ ! -f "libraries/net/neoforged/neoforge/$NEO/unix_args.txt" ]; then
  retry as_mc "curl -fsSL -o neoforge-installer.jar https://maven.neoforged.net/releases/net/neoforged/neoforge/$NEO/neoforge-$NEO-installer.jar"
  retry as_mc "java -jar neoforge-installer.jar --install-server > neoforge-install.log 2>&1" \
    || { echo "NeoForge-Installation fehlgeschlagen:"; tail -20 neoforge-install.log; exit 1; }
  rm -f neoforge-installer.jar neoforge-installer.jar.log
fi

step "Modpack von GitHub (nur Server-Mods)"
[ -f packwiz-installer-bootstrap.jar ] || retry as_mc "curl -fsSL -o packwiz-installer-bootstrap.jar $BOOT"
retry as_mc "java -jar packwiz-installer-bootstrap.jar -g -s server $PACK"
echo "Mods: $(ls mods | wc -l)"

step "Java-Optionen ($RAM_GB GB)"
cat > user_jvm_args.txt <<EOF
-Xms${RAM_GB}G
-Xmx${RAM_GB}G
-XX:+UseG1GC
-XX:+ParallelRefProcEnabled
-XX:MaxGCPauseMillis=200
-XX:+UnlockExperimentalVMOptions
-XX:+DisableExplicitGC
-XX:+AlwaysPreTouch
-XX:G1NewSizePercent=40
-XX:G1MaxNewSizePercent=50
-XX:G1HeapRegionSize=16M
-XX:G1ReservePercent=15
-XX:G1HeapWastePercent=5
-XX:G1MixedGCCountTarget=4
-XX:InitiatingHeapOccupancyPercent=20
-XX:G1MixedGCLiveThresholdPercent=90
-XX:G1RSetUpdatingPauseTimePercent=5
-XX:SurvivorRatio=32
-XX:+PerfDisableSharedMem
-XX:MaxTenuringThreshold=1
EOF

step "Server-Einstellungen"
if [ ! -f server.properties ]; then
  cat > server.properties <<'EOF'
motd=§5§lVoid §6§l& §c§lDraconic
max-players=6
difficulty=normal
view-distance=10
simulation-distance=8
white-list=true
enforce-whitelist=true
allow-flight=true
spawn-protection=0
max-tick-time=-1
online-mode=true
server-port=25565
EOF
fi
if [ "$ACCEPT_EULA" = yes ]; then
  printf '#Akzeptiert beim Einrichten: https://aka.ms/MinecraftEULA\neula=true\n' > eula.txt
else
  echo "EULA nicht akzeptiert (ACCEPT_EULA=yes fehlt). Vor dem Start eula=true in $MC_DIR/eula.txt setzen."
fi

step "Whitelist und OP: $PLAYERS"
wl='[]'; ops='[]'
for p in $PLAYERS; do
  r=$(curl -fsS "https://api.mojang.com/users/profiles/minecraft/$p") || { echo "Spieler $p nicht gefunden, übersprungen."; continue; }
  uuid=$(echo "$r" | jq -r .id | sed -E 's/(.{8})(.{4})(.{4})(.{4})(.{12})/\1-\2-\3-\4-\5/')
  name=$(echo "$r" | jq -r .name)
  wl=$(echo "$wl" | jq --arg u "$uuid" --arg n "$name" '. + [{uuid:$u, name:$n}]')
  ops=$(echo "$ops" | jq --arg u "$uuid" --arg n "$name" '. + [{uuid:$u, name:$n, level:4, bypassesPlayerLimit:true}]')
done
echo "$wl" > whitelist.json
echo "$ops" > ops.json

step "Start- und Hilfsskripte"
cat > start.sh <<EOF
#!/usr/bin/env bash
# Holt vor jedem Start die neueste Pack-Version, dann NeoForge.
cd "\$(dirname "\$0")"
java -jar packwiz-installer-bootstrap.jar -g -s server $PACK || echo "Pack-Update fehlgeschlagen, starte mit den vorhandenen Mods."
exec java @user_jvm_args.txt @libraries/net/neoforged/neoforge/$NEO/unix_args.txt nogui
EOF
chmod +x start.sh
cat > /usr/local/bin/mc <<EOF
#!/usr/bin/env bash
# mc start|stop|restart|status|console|log|cmd "<befehl>"
S=void-draconic
case "\${1:-}" in
  start|stop|restart|status) systemctl "\$1" \$S ;;
  console) echo "Konsole verlassen: Strg+B, dann D"; sudo -u $MC_USER tmux attach -t mc ;;
  log) tail -n 100 -f $MC_DIR/logs/latest.log ;;
  cmd) shift; sudo -u $MC_USER tmux send-keys -t mc "\$*" Enter; sleep 2; tail -n 15 $MC_DIR/logs/latest.log ;;
  *) echo "mc start|stop|restart|status|console|log|cmd \"<befehl>\"" ;;
esac
EOF
chmod +x /usr/local/bin/mc
chown -R "$MC_USER:$MC_USER" "$MC_DIR"

if [ "${SKIP_SYSTEMD:-0}" != 1 ]; then
  step "Dienst (startet automatisch und nach Absturz neu)"
  cat > /etc/systemd/system/void-draconic.service <<EOF
[Unit]
Description=Void & Draconic Minecraft-Server
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
User=$MC_USER
WorkingDirectory=$MC_DIR
ExecStart=/usr/bin/tmux new-session -d -s mc $MC_DIR/start.sh
ExecStop=/usr/bin/tmux send-keys -t mc "stop" Enter
ExecStop=/bin/bash -c 'while /usr/bin/tmux has-session -t mc 2>/dev/null; do sleep 1; done'
TimeoutStopSec=180
# tmux beendet sich auch bei einem Absturz sauber, deshalb "always". "mc stop" stoppt trotzdem dauerhaft.
Restart=always
RestartSec=20

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable void-draconic >/dev/null
fi

if [ "${SKIP_FIREWALL:-0}" != 1 ]; then
  step "Firewall"
  apt-get install -y -qq ufw >/dev/null
  ufw allow OpenSSH >/dev/null
  ufw allow 25565/tcp comment "Minecraft" >/dev/null
  ufw allow 24454/udp comment "Simple Voice Chat" >/dev/null
  ufw --force enable >/dev/null
  ufw status | grep -E "22|25565|24454"
fi

step "Fertig"
cat <<EOF
Ordner:   $MC_DIR
Starten:  mc start      (danach: mc log, Konsole: mc console)
Befehle:  mc cmd "whitelist add Name"

Nach dem ersten Start:
  mc cmd "chunky radius 2000"   dann   mc cmd "chunky start"
EOF
