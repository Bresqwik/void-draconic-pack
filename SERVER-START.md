# Server – Betrieb und Neuaufbau

Der Server läuft seit dem 07.10.2026. Diese Seite beschreibt den aktuellen Stand, die tägliche Bedienung und wie man ihn bei Bedarf mit einem Befehl neu aufsetzt.

## Steckbrief

| | |
|---|---|
| **Adresse im Spiel** | `mc-void-draconic.duckdns.org` (Port 25565, steht in der Prism-Instanz schon in der Serverliste) |
| **Dashboard** | [mc-void-draconic.duckdns.org](https://mc-void-draconic.duckdns.org) (mit Passwort) |
| **Hoster** | Tube-Hosting, Tarif Large, IP `193.111.248.12` |
| **Hardware** | AMD EPYC 7542, 12 Kerne, 31 GB RAM, 197 GB SSD |
| **System** | Debian 12, NeoForge 21.1.252, Java 21 (Temurin) |
| **Minecraft** | 16 GB RAM, max. 6 Spieler, Whitelist: stman476, MarkMero, Prexynation |
| **Pack** | wird vor jedem Start automatisch von GitHub aktualisiert (nur Server-Mods) |

## Welt

Die Welt ist mit Chunky vorgeneriert, deshalb hakt beim Erkunden nichts:

| Dimension | Radius | Chunks | Dauer |
|---|---|---|---|
| Oberwelt | 10.000 Blöcke | 1.565.001 | 5:09 h (etwa 70 Chunks/s) |
| Nether | 2.000 Blöcke | 63.001 | 0:19 h |
| End | 2.000 Blöcke | 63.001 | 0:16 h |

**C2ME** (nur auf dem Server) verteilt die Weltgenerierung auf mehrere Kerne. Ohne C2ME schaffte der Server nur 6–9 Chunks pro Sekunde, mit C2ME rund 50–70. `sync-chunk-writes=false` spart zusätzlich Schreiblast.

**Weiter vorgenerieren:** Der Dashboard-Dienst hat einen Wächter, der Chunky pausiert, sobald jemand online ist, und 60 Sekunden nach dem letzten Logout weitermacht. Auftrag erteilen:

```bash
echo '{"active": true, "world": "minecraft:overworld", "radius": 20000}' > /var/lib/mc-dashboard/pregen-job.json
```

Den Fortschritt zeigt das Dashboard. Ist der Auftrag fertig, setzt der Wächter `"active": false`.

## Backups

| Was | Wann | Wo | Aufbewahrung |
|---|---|---|---|
| Simple Backups (komplette Welt) | alle 4 Stunden, solange Spieler online sind | `/opt/void-draconic/simplebackups/world` | die letzten 3, höchstens 60 GB |
| Tägliches Backup | jeden Tag um 04:00, auch ohne Spieler | wie oben | wie oben |
| Cloud-Kopie | direkt nach dem täglichen Backup | Google Drive: `Minecraft Modpack - Void & Draconic/Backups` | 8 Tage |

Ein Backup ist zurzeit etwa 14 GB groß. Den letzten Upload zeigt das Dashboard.

**Zurückspielen** (Beispiel mit dem Backup von 04:00):

```bash
mc stop
cd /opt/void-draconic
mv world world-defekt
sudo -u minecraft unzip -q simplebackups/world/world_2026-10-08_04-00-01.zip
mc start
```

Liegt das Backup nur noch in Google Drive: `rclone copy "gdrive:Minecraft Modpack - Void & Draconic/Backups/<Datei>.zip" /opt/void-draconic/simplebackups/world/`, dann wie oben.

## Bedienung

| Befehl | Wirkung |
|---|---|
| `mc start` / `mc stop` / `mc restart` | Server starten, stoppen, neu starten. Nach einem Absturz startet er von selbst neu. |
| `mc log` | laufendes Log (beenden mit Strg+C) |
| `mc console` | Server-Konsole (verlassen mit Strg+B, dann D) |
| `mc cmd "whitelist add Name"` | einen Befehl an den Server schicken |
| `mc cmd "neoforge tps"` | Leistung je Dimension, Ziel: 20 TPS |
| `systemctl start mc-backup-cloud` | sofort ein Backup anlegen und nach Drive hochladen |

Das Dashboard zeigt live Spieler, TPS, CPU, RAM, Ereignisse, Vorgenerierung, Backups und Bestenlisten. Die zweite Zeile der Serverbeschreibung (MOTD) wird ebenfalls live aktualisiert.

## Zugangsdaten trägt Stefan selbst ein

Claude liest und tippt keine Passwörter oder Tokens. Diese Befehle fragen sie verdeckt ab:

| Wofür | Befehl auf dem Server |
|---|---|
| DuckDNS-Token | `nano /etc/void-draconic/duckdns.env`, Token bei `DUCKDNS_TOKEN=` eintragen, testen mit `duckdns-update` |
| Google Drive | am PC `rclone authorize "drive"` ausführen und bei Google anmelden, dann auf dem Server `gdrive-token` und die komplette Ausgabe einfügen |
| Dashboard-Login | `dashboard-passwort` |

Das RCON-Passwort für Dashboard und Wächter erzeugt das Setup-Skript zufällig. Port 25575 bleibt in der Firewall zu.

## Neuaufbau mit einem Befehl

Falls der Server neu aufgesetzt werden muss oder umzieht: Debian 12 bestellen, diesen SSH-Schlüssel eintragen, damit Claude einrichten kann,

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAV3VTWbgrcZJoFb2BZ2aMuEjI317v6KUV2YPnp++XK5 stefan@DESKTOP-EO3LRT5
```

und dann als root:

```bash
curl -fsSL https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/server/setup-linux.sh -o setup-linux.sh
ACCEPT_EULA=yes bash setup-linux.sh
```

`ACCEPT_EULA=yes` heißt: Ihr stimmt der [Minecraft-EULA](https://aka.ms/MinecraftEULA) zu. Das Skript [`server/setup-linux.sh`](server/setup-linux.sh) baut den Stand oben komplett nach:

- Java 21, NeoForge 21.1.252 und das Pack von GitHub (geladen über den genauen Commit, damit nie eine veraltete Version kommt)
- 16 GB RAM mit optimierten Java-Optionen, RCON nur lokal, `sync-chunk-writes=false`
- Whitelist und OP für stman476, MarkMero und Prexynation (änderbar mit `PLAYERS="..."`)
- Dienst `void-draconic`, der beim Hochfahren und nach Abstürzen neu startet und vorher das Pack aktualisiert
- Backups: tägliches Backup um 04:00 mit Upload nach Google Drive, DuckDNS-Update alle 5 Minuten
- Dashboard mit Caddy (automatisches HTTPS) und Datensammler `mc-dashboard`
- Firewall: 22 (SSH), 25565/tcp (Minecraft), 24454/udp (Voice Chat), 80 und 443 (Dashboard)
- die Befehle `mc`, `gdrive-token`, `dashboard-passwort`, `duckdns-update`

Danach die drei Zugangsdaten eintragen (siehe oben), mit `mc start` starten und die Welt aus dem letzten Drive-Backup zurückspielen. Das Skript kann gefahrlos erneut laufen: Welt, Whitelist, Zugangsdaten und Backups bleiben erhalten.

Weitere Optionen: `RAM_GB=12`, `DUCKDNS_DOMAIN=anderer-name`, `SKIP_DASHBOARD=1`, `SKIP_FIREWALL=1`, `SKIP_SYSTEMD=1`.
