#!/usr/bin/env bash
# Void & Draconic – Einrichtung auf einem frischen Linux-Server (Debian 12/13 oder Ubuntu 24.04), als root.
# Baut den Stand des Tube-Servers nach: Minecraft-Dienst, Dashboard mit HTTPS, Backups nach Google Drive, DuckDNS.
#
#   curl -fsSL https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/server/setup-linux.sh -o setup-linux.sh
#   ACCEPT_EULA=yes bash setup-linux.sh
#
# Einstellbar per Umgebungsvariable:
#   ACCEPT_EULA=yes        Minecraft-EULA (https://aka.ms/MinecraftEULA) akzeptieren. Ohne das startet der Server nicht.
#   RAM_GB=16              Arbeitsspeicher für Minecraft
#   PLAYERS="a b"          Spieler für Whitelist und OP
#   DUCKDNS_DOMAIN=name    DuckDNS-Name (ohne .duckdns.org). Den Token trägt man selbst in /etc/void-draconic/duckdns.env ein.
#   MC_DIR=/opt/void-draconic
#   SKIP_SYSTEMD=1         Keine Dienste einrichten (z. B. in Containern)
#   SKIP_FIREWALL=1        ufw nicht anfassen
#   SKIP_DASHBOARD=1       Kein Dashboard (Caddy, Datensammler)
#
# Das Skript kann gefahrlos erneut laufen: Welt, Whitelist, Zugangsdaten und Backups bleiben erhalten.
set -euo pipefail

MC_DIR=${MC_DIR:-/opt/void-draconic}
MC_USER=minecraft
NEO=21.1.252
RAM_GB=${RAM_GB:-16}
PLAYERS=${PLAYERS:-"stman476 MarkMero Prexynation"}
DUCKDNS_DOMAIN=${DUCKDNS_DOMAIN:-mc-void-draconic}
ACCEPT_EULA=${ACCEPT_EULA:-no}
REPO=Bresqwik/void-draconic-pack
BOOT=https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar

step() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Bitte als root ausführen."; exit 1; }
# Downloads können sporadisch abbrechen: bis zu 3 Versuche
retry() { local n; for n in 1 2 3; do "$@" && return 0; echo "Versuch $n fehlgeschlagen, neuer Versuch in 10 s ..."; sleep 10; done; return 1; }
# Repo-Dateien über den genauen Commit laden (raw.githubusercontent.com hält "main" einige Minuten im Cache)
SHA=$(curl -fsS -m 10 -H "Accept: application/vnd.github.sha" "https://api.github.com/repos/$REPO/commits/main" 2>/dev/null || true)
[[ $SHA =~ ^[0-9a-f]{40}$ ]] || SHA=main
RAW=https://raw.githubusercontent.com/$REPO/$SHA
fetch() { retry curl -fsSL -o "$2" "$RAW/$1"; }

step "Pakete"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl unzip jq tmux ca-certificates gnupg python3 rclone >/dev/null

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

step "NeoForge $NEO"
if [ ! -f "libraries/net/neoforged/neoforge/$NEO/unix_args.txt" ]; then
  retry as_mc "curl -fsSL -o neoforge-installer.jar https://maven.neoforged.net/releases/net/neoforged/neoforge/$NEO/neoforge-$NEO-installer.jar"
  retry as_mc "java -jar neoforge-installer.jar --install-server > neoforge-install.log 2>&1" \
    || { echo "NeoForge-Installation fehlgeschlagen:"; tail -20 neoforge-install.log; exit 1; }
  rm -f neoforge-installer.jar neoforge-installer.jar.log
fi

step "Modpack von GitHub (nur Server-Mods, Commit ${SHA:0:7})"
[ -f packwiz-installer-bootstrap.jar ] || retry as_mc "curl -fsSL -o packwiz-installer-bootstrap.jar $BOOT"
retry as_mc "java -jar packwiz-installer-bootstrap.jar -g -s server $RAW/pack.toml"
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
# Pflichtwerte auch in bestehenden Dateien setzen:
#   RCON nur lokal für Dashboard und Pregen-Wächter (Port 25575 bleibt in der Firewall zu),
#   sync-chunk-writes=false spart beim Welt-Generieren viel Schreiblast.
setprop() { if grep -q "^$1=" server.properties; then sed -i "s|^$1=.*|$1=$2|" server.properties; else echo "$1=$2" >> server.properties; fi; }
setprop enable-rcon true
setprop rcon.port 25575
setprop sync-chunk-writes false
setprop enable-status true
grep -q '^rcon.password=.\+' server.properties || setprop rcon.password "$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32)"
chmod 600 server.properties
if [ "$ACCEPT_EULA" = yes ]; then
  printf '#Akzeptiert beim Einrichten: https://aka.ms/MinecraftEULA\neula=true\n' > eula.txt
elif ! grep -q 'eula=true' eula.txt 2>/dev/null; then
  echo "EULA nicht akzeptiert (ACCEPT_EULA=yes fehlt). Vor dem Start eula=true in $MC_DIR/eula.txt setzen."
fi

step "Whitelist und OP: $PLAYERS"
if [ -s whitelist.json ] && [ "$(jq length whitelist.json)" -gt 0 ]; then
  echo "Whitelist besteht schon ($(jq -r '[.[].name] | join(", ")' whitelist.json)), bleibt unverändert."
else
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
fi

step "Start- und Hilfsskripte"
fetch server/start.sh start.sh
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

step "Backups nach Google Drive und DuckDNS"
# Ablauf: Simple Backups sichert alle 4 Stunden, solange Spieler online sind (config/simplebackups-common.toml).
# Täglich um 04:00 erzwingt mc-backup-daily zusätzlich ein Backup (auch ohne Spieler).
# mc-backup-cloud (Timer alle 10 Minuten) lädt jedes fertige Backup nach Google Drive, prüft Größe und MD5 dort
# und löscht es erst dann auf dem Server. In Drive bleiben die Backups 8 Tage.
install -d -m 700 /etc/void-draconic
fetch server/mc-backup-daily /usr/local/bin/mc-backup-daily
fetch server/mc-backup-cloud /usr/local/bin/mc-backup-cloud
cat > /usr/local/bin/gdrive-token <<'EOF'
#!/usr/bin/env bash
# Fragt den Google-Drive-Token (aus "rclone authorize drive" am PC) unsichtbar ab und trägt ihn ins Remote gdrive ein.
# Akzeptiert das JSON {...} älterer rclone-Versionen und die Base64-Hülle neuerer (ab 1.7x); doppelt Eingefügtes wird ignoriert.
echo "Token einfügen (die ganze Ausgabe von rclone authorize), dann Enter:"
read -rs T; echo
[ -n "$T" ] || { echo "Kein Token eingegeben."; exit 1; }
TOK=$(GT="$T" python3 - <<'PY'
import base64, json, os, sys
s = os.environ["GT"].replace("\r", "").strip()
def first_json(t):
    i = t.find("{")
    return json.JSONDecoder().raw_decode(t[i:])[0] if i >= 0 else None
def unwrap(o):
    if isinstance(o, dict) and "token" in o and "access_token" not in o:
        t = o["token"]
        return json.loads(t) if isinstance(t, str) else t
    return o
o = None
try: o = first_json(s)
except ValueError: pass
if o is None:
    for word in s.split():
        for dec in (base64.b64decode, base64.urlsafe_b64decode):
            try: o = first_json(dec(word + "=" * (-len(word) % 4)).decode()); break
            except Exception: pass
        if o: break
o = unwrap(o)
if not isinstance(o, dict) or "access_token" not in o: sys.exit(1)
print(json.dumps(o, separators=(",", ":")))
PY
) || { unset T; echo "Das sieht nicht wie ein rclone-Token aus. Bitte die komplette Ausgabe von 'rclone authorize drive' einfügen."; exit 1; }
unset T
rclone config update gdrive token "$TOK" --non-interactive >/dev/null && unset TOK || { echo "Eintragen fehlgeschlagen."; exit 1; }
if rclone lsd gdrive: >/dev/null 2>&1; then echo "Google Drive verbunden."; else echo "Token gespeichert, aber Google Drive antwortet nicht."; fi
EOF
cat > /usr/local/bin/duckdns-update <<'EOF'
#!/usr/bin/env bash
# Hält den DuckDNS-Namen auf der aktuellen IP. Domain und Token stehen in /etc/void-draconic/duckdns.env:
#   DUCKDNS_DOMAIN=meinname      (ohne .duckdns.org)
#   DUCKDNS_TOKEN=...            (von duckdns.org, trägt Stefan selbst ein)
f=/etc/void-draconic/duckdns.env
[ -r "$f" ] || exit 0
. "$f"
[ -n "${DUCKDNS_DOMAIN:-}" ] && [ -n "${DUCKDNS_TOKEN:-}" ] || exit 0
r=$(curl -fsS -m 20 "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=")
[ "$r" = OK ] && echo "DuckDNS aktualisiert" || { echo "DuckDNS-Fehler: $r"; exit 1; }
EOF
chmod 755 /usr/local/bin/mc-backup-cloud /usr/local/bin/mc-backup-daily /usr/local/bin/gdrive-token /usr/local/bin/duckdns-update
if [ ! -f /etc/void-draconic/duckdns.env ]; then
  printf 'DUCKDNS_DOMAIN=%s\nDUCKDNS_TOKEN=\n' "$DUCKDNS_DOMAIN" > /etc/void-draconic/duckdns.env
  chmod 600 /etc/void-draconic/duckdns.env
fi
# rclone-Remote ohne Token anlegen (scope drive.file: rclone sieht nur Dateien, die es selbst angelegt hat)
RC=/root/.config/rclone/rclone.conf
install -d -m 700 /root/.config/rclone
grep -q '^\[gdrive\]' "$RC" 2>/dev/null || printf '[gdrive]\ntype = drive\nscope = drive.file\n\n' >> "$RC"
chmod 600 "$RC"
if [ "${SKIP_SYSTEMD:-0}" != 1 ]; then
  printf '[Unit]\nDescription=Tägliches Backup (auch ohne Spieler) und Upload nach Google Drive\nAfter=network-online.target\n\n[Service]\nType=oneshot\nExecStart=/usr/local/bin/mc-backup-daily\nNice=10\nIOSchedulingClass=idle\nTimeoutStartSec=4h\n' > /etc/systemd/system/mc-backup-cloud.service
  printf '[Unit]\nDescription=Tägliches Backup (Timer)\n\n[Timer]\nOnCalendar=*-*-* 04:00:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n' > /etc/systemd/system/mc-backup-cloud.timer
  printf '[Unit]\nDescription=Fertige Backups nach Google Drive laden, prüfen und lokal löschen\nAfter=network-online.target\n\n[Service]\nType=oneshot\nExecStart=/usr/local/bin/mc-backup-cloud\nNice=10\nIOSchedulingClass=idle\nTimeoutStartSec=3h\n' > /etc/systemd/system/mc-backup-sync.service
  printf '[Unit]\nDescription=Backups nach Google Drive (alle 10 Minuten prüfen)\n\n[Timer]\nOnCalendar=*:0/10\nRandomizedDelaySec=30\n\n[Install]\nWantedBy=timers.target\n' > /etc/systemd/system/mc-backup-sync.timer
  rm -rf /etc/systemd/system/mc-backup-cloud.service.d /etc/systemd/system/mc-backup-cloud.timer.d
  printf '[Unit]\nDescription=DuckDNS aktualisieren\nAfter=network-online.target\n\n[Service]\nType=oneshot\nExecStart=/usr/local/bin/duckdns-update\n' > /etc/systemd/system/duckdns-update.service
  printf '[Unit]\nDescription=DuckDNS aktualisieren (Timer)\n\n[Timer]\nOnCalendar=*:0/5\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n' > /etc/systemd/system/duckdns-update.timer
  systemctl daemon-reload
  systemctl enable --now mc-backup-cloud.timer mc-backup-sync.timer duckdns-update.timer >/dev/null
fi

if [ "${SKIP_DASHBOARD:-0}" != 1 ] && [ "${SKIP_SYSTEMD:-0}" != 1 ]; then
  step "Dashboard (https://$DUCKDNS_DOMAIN.duckdns.org, mit Passwort)"
  if ! command -v caddy >/dev/null; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https >/dev/null
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy >/dev/null
  fi
  apt-get install -y -qq python3-bcrypt >/dev/null
  install -d /opt/mc-dashboard /var/www/mc-dashboard/data /var/lib/mc-dashboard
  fetch server/dashboard/collect.py /opt/mc-dashboard/collect.py
  fetch server/dashboard/auth.py /opt/mc-dashboard/auth.py
  fetch server/dashboard/index.html /var/www/mc-dashboard/index.html
  fetch server/dashboard/mc-dashboard.service /etc/systemd/system/mc-dashboard.service
  fetch server/dashboard/mc-dashboard-auth.service /etc/systemd/system/mc-dashboard-auth.service
  chmod 755 /opt/mc-dashboard/collect.py /opt/mc-dashboard/auth.py
  # Anmeldung über die eigene Login-Seite: Caddy fragt per forward_auth bei mc-dashboard-auth nach.
  # Ohne /etc/caddy/dashboard.env lässt der Login-Dienst niemanden hinein.
  fetch server/dashboard/Caddyfile /etc/caddy/Caddyfile
  sed -i "s/^mc-void-draconic\.duckdns\.org {/$DUCKDNS_DOMAIN.duckdns.org {/" /etc/caddy/Caddyfile
  rm -f /etc/systemd/system/caddy.service.d/dashboard.conf
  cat > /usr/local/bin/dashboard-passwort <<EOF
#!/usr/bin/env bash
# Legt Benutzer und Passwort für das Dashboard fest. Gespeichert wird nur der Hash (/etc/caddy/dashboard.env).
# Alle bestehenden Anmeldungen werden dabei ungültig.
set -e
read -rp "Benutzername [void]: " U; U=\${U:-void}
[[ \$U =~ ^[A-Za-z0-9._-]+\$ ]] || { echo "Nur Buchstaben, Ziffern, Punkt, Strich, Unterstrich."; exit 1; }
read -rsp "Passwort: " P1; echo
read -rsp "Passwort wiederholen: " P2; echo
[ "\$P1" = "\$P2" ] || { echo "Passwörter stimmen nicht überein."; exit 1; }
[ \${#P1} -ge 8 ] || { echo "Bitte mindestens 8 Zeichen."; exit 1; }
H=\$(printf "%s\n" "\$P1" | caddy hash-password); unset P1 P2
printf "DASH_USER=%s\nDASH_HASH=%s\n" "\$U" "\$H" > /etc/caddy/dashboard.env
chmod 640 /etc/caddy/dashboard.env; chgrp caddy /etc/caddy/dashboard.env
echo "Gespeichert. Login: \$U – https://$DUCKDNS_DOMAIN.duckdns.org"
EOF
  chmod 755 /usr/local/bin/dashboard-passwort
  systemctl daemon-reload
  systemctl enable --now mc-dashboard mc-dashboard-auth >/dev/null
  systemctl restart mc-dashboard mc-dashboard-auth caddy
  [ -s /etc/caddy/dashboard.env ] || echo "Dashboard-Login fehlt noch: dashboard-passwort"
fi

if [ "${SKIP_FIREWALL:-0}" != 1 ]; then
  step "Firewall"
  apt-get install -y -qq ufw >/dev/null
  ufw allow OpenSSH >/dev/null
  ufw allow 25565/tcp comment "Minecraft" >/dev/null
  ufw allow 24454/udp comment "Simple Voice Chat" >/dev/null
  if [ "${SKIP_DASHBOARD:-0}" != 1 ]; then
    ufw allow 80/tcp comment "Dashboard (HTTP, Zertifikat)" >/dev/null
    ufw allow 443/tcp comment "Dashboard (HTTPS)" >/dev/null
  fi
  ufw --force enable >/dev/null
  ufw status | grep -E "22|25565|24454|80|443" || true
fi

step "Fertig"
cat <<EOF
Ordner:    $MC_DIR
Starten:   mc start      (danach: mc log, Konsole: mc console)
Befehle:   mc cmd "whitelist add Name"
Dashboard: https://$DUCKDNS_DOMAIN.duckdns.org

Welt vorgenerieren (Dashboard-Wächter pausiert, sobald jemand online ist):
  echo '{"active": true, "world": "minecraft:overworld", "radius": 5000}' > /var/lib/mc-dashboard/pregen-job.json

Noch selbst einzutragen (Zugangsdaten gibt nur Stefan ein):
  DuckDNS:      nano /etc/void-draconic/duckdns.env   (DUCKDNS_TOKEN)
  Google Drive: am PC "rclone authorize drive", dann hier: gdrive-token
  Dashboard:    dashboard-passwort
  Testen:       duckdns-update   und   mc-backup-cloud
EOF
