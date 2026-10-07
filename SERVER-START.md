# Server-Start – Plan für den neuen Server

Der alte Server ist seit dem 07.10.2026 weg. Pack, Client und Skripte sind fertig. Sobald ein neuer Server da ist, läuft Minecraft nach etwa 20 Minuten.

## Schon entschieden (07.10.2026)

| Frage | Entscheidung |
|---|---|
| Welcher Server? | Linux-Mietserver mit schneller CPU, kommt noch diese Woche |
| Panel? | **ohne**, nur Minecraft, eingerichtet mit dem Setup-Skript |
| Farmen offline? | **ja**: `force_load_mode "always"`, 25 Chunks pro Spieler, im Pack voreingestellt |
| Backups? | Simple Backups auf dem Server, dazu täglich eine Kopie nach **Google Drive** |
| Adresse? | **neuer DuckDNS-Name** |

## 1. Server bestellen

**Lehre vom alten Server:** Ein Xeon mit 2,0–2,6 GHz hat die Welt nur mit 5–6 Chunks pro Sekunde erzeugt. Beim Erkunden hat das deutlich gehakt. Für Modpacks zählt vor allem der **Takt pro Kern**, nicht die Zahl der Kerne.

| Bereich | Minimum | Empfohlen |
|---|---|---|
| Prozessor | 4 Kerne, Boost ab 4,5 GHz | 6+ Kerne, aktuelle Ryzen-Generation (7000/9000), dedizierte Kerne |
| RAM | 16 GB | 24–32 GB (12 GB für Minecraft, Rest für System und Backups) |
| Speicher | 60 GB NVMe | 100–200 GB NVMe |
| System | Debian 12 oder Ubuntu 24.04 | Debian 12 |
| Netz | öffentliche IPv4 | 25+ Mbit/s Upload |

**Bei der Bestellung:**
- Preis und CPU-Modell beim Anbieter prüfen. Steht nur „vCPU“ ohne Modell und Takt da, ist es meist ein langsamer Server-Prozessor.
- Debian 12 wählen und diesen SSH-Schlüssel eintragen, damit Claude den Server direkt einrichten kann:

  ```
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAV3VTWbgrcZJoFb2BZ2aMuEjI317v6KUV2YPnp++XK5 stefan@DESKTOP-EO3LRT5
  ```

- Auf [duckdns.org](https://www.duckdns.org) einen neuen Namen anlegen.

## 2. Einrichtung

Ein Befehl als root auf dem neuen Server. `<Kollege>` durch den Minecraft-Namen ersetzen und `<name>` durch den DuckDNS-Namen ohne `.duckdns.org`:

```bash
curl -fsSL https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/server/setup-linux.sh -o setup-linux.sh
ACCEPT_EULA=yes PLAYERS="stman476 MarkMero <Kollege>" DUCKDNS_DOMAIN=<name> bash setup-linux.sh
```

Das Skript [`server/setup-linux.sh`](server/setup-linux.sh) erledigt:

- Java 21 (Eclipse Temurin) und NeoForge 21.1.252 installieren
- das Pack direkt von GitHub laden, nur die Server-Mods
- 12 GB RAM mit optimierten Java-Optionen einstellen
- Whitelist und OP für alle in `PLAYERS` eintragen
- einen Dienst anlegen, der Minecraft beim Hochfahren und nach einem Absturz neu startet. Vor jedem Start holt er die neueste Pack-Version.
- die Firewall öffnen: 22 (SSH), 25565/tcp (Minecraft), 24454/udp (Voice Chat)
- Timer einrichten: täglich um 4:30 das neueste Backup nach Google Drive (dort 8 Tage aufbewahrt), alle 5 Minuten die IP bei DuckDNS aktualisieren
- den Befehl `mc` anlegen: `mc start`, `mc stop`, `mc log`, `mc console`, `mc cmd "whitelist add Name"`

`ACCEPT_EULA=yes` heißt: Ihr stimmt der [Minecraft-EULA](https://aka.ms/MinecraftEULA) zu. Ohne Zustimmung startet der Server nicht.

### Zugangsdaten trägt Stefan selbst ein

Claude liest und tippt keine Passwörter oder Tokens. Diese zwei Schritte macht Stefan auf dem Server:

1. **DuckDNS-Token:** `nano /etc/void-draconic/duckdns.env`, dann bei `DUCKDNS_TOKEN=` den Token von duckdns.org einfügen. Testen mit `duckdns-update`, die Ausgabe sollte „DuckDNS aktualisiert“ lauten.
2. **Google Drive:** `rclone config` aufrufen
   - `n` für ein neues Remote, Name **`gdrive`**, Typ **`drive`**
   - Client-ID und Secret leer lassen, Scope **`drive.file`**. Dann sieht rclone nur seine eigenen Backup-Dateien.
   - Bei „Use web browser to automatically authenticate?“ **`n`** wählen und die angezeigte Anleitung befolgen: Auf dem PC [rclone für Windows](https://rclone.org/downloads/) entpacken, dort `rclone authorize "drive"` ausführen, sich bei Google anmelden und den Code zurückkopieren.
   - Testen mit `mc-backup-cloud`. Sobald es das erste Backup gibt, erscheint es in Google Drive im Ordner `Void-Draconic-Backups`.

## 3. Checkliste nach dem ersten Start

- [ ] **Beitreten:** alle Spieler testen
- [ ] **Voice Chat:** im Spiel Taste `V` und gegenseitig hören (UDP 24454)
- [ ] **Welt vorgenerieren** (läuft im Hintergrund, Dauer je nach Prozessor):
  - Oberwelt: `mc cmd "chunky radius 2000"`, dann `mc cmd "chunky start"`
  - danach Nether: `chunky world minecraft:the_nether`, `chunky radius 1000`, `chunky start`
  - danach End: `chunky world minecraft:the_end`, `chunky radius 1000`, `chunky start`
- [ ] **Forceload prüfen:** `grep force_load_mode /opt/void-draconic/config/ftbchunks-world.snbt` zeigt `"always"`
- [ ] **Backups:** Nach etwa 2 Stunden Spielzeit liegt das erste Simple-Backup vor. Spätestens am nächsten Morgen ist es in Google Drive.
- [ ] **Leistung prüfen:** `mc cmd "spark tps"`. Ziel sind 20 TPS und unter 50 ms pro Tick.
- [ ] **Kollege:** Prism-Instanz über den [Import-Link](README.md#installation) einrichten

## 4. Schon fertig

- Modpack mit 220 Mods, Auto-Update über GitHub
- Prism-Instanz zum Importieren mit einem Link
- Forceload „always“ im Pack voreingestellt
- Server-Icons und wechselnde Beschreibung (MiniMOTD), Noisium für schnellere Weltgenerierung
- Setup-Skript mit Cloud-Backup und DuckDNS, getestet in einem Debian-12-Container
