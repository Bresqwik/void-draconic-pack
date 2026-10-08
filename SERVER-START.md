# Server – Betrieb und Neuaufbau

Der Server läuft seit dem 07.10.2026. Diese Seite beschreibt den aktuellen Stand, die tägliche Bedienung und wie man ihn bei Bedarf mit einem Befehl neu aufsetzt.

## Steckbrief

| | |
|---|---|
| **Adresse im Spiel** | `mc-void-draconic.duckdns.org` (Port 25565, steht in der Prism-Instanz schon in der Serverliste) |
| **Dashboard** | [mc-void-draconic.duckdns.org](https://mc-void-draconic.duckdns.org) (mit Passwort) |
| **Hoster** | Tube-Hosting, Tarif Large, IP `193.111.248.12` |
| **Hardware** | AMD EPYC 7542, 12 Kerne, 31 GB RAM, 197 GB SSD |
| **System** | Debian 12, Minecraft 1.20.1, Forge 47.4.26, Java 17 (Temurin) |
| **Minecraft** | 16 GB RAM, max. 6 Spieler, Whitelist: stman476, MarkMero, Prexynation |
| **Pack** | wird vor jedem Start automatisch von GitHub aktualisiert (nur Server-Mods) |
| **Erweitern** | laut Support je 30 GB NVMe 1 €/Monat, je 2 GB RAM 1 €/Monat, jederzeit per Ticket. Fehlt nur Speicher, ist das viel günstiger als ein größerer Tarif. |

## Welt

Seit dem 08.10.2026 läuft der Server auf **Minecraft 1.20.1 mit Forge** (Pack 0.4) und einer neuen Welt. Die alte 1.21.1-Welt mit dem alten Pack liegt geprüft in Google Drive unter `Minecraft Modpack - Void & Draconic/Archiv/void-draconic-1.21.1-2026-10-08.tar.zst` (21,6 GB, MD5 geprüft). Zurückholen: Datei herunterladen und mit `tar -I zstd -xf … -C /opt` auspacken (ergibt `/opt/void-draconic`).

Dimensionen der neuen Welt: Oberwelt, Nether, End, Aether, Twilight Forest, Otherside, Everbright und Everdawn (Blue Skies), Bumblezone, Alfheim (Mythic Botany) und kleine Spezial-Dimensionen (Blood-Magic-Dungeon, Iron's Taschendimension, Inneres des Wither Storm).

**Erze:** Doppelte Erze werden gar nicht erst erzeugt (Blei und Uran nur von Mekanism, Silber nur von Immersive Engineering, siehe `kubejs/data/README-erze.md`). Almost Unified gibt Mekanism Vorrang bei Rezept-Ergebnissen.

**Vorgenerieren:** C2ME gibt es für Forge 1.20.1 nur als Alpha, deshalb ist es nicht drin. Der Dashboard-Dienst hat einen Wächter, der Chunky pausiert, sobald jemand online ist (Schalter im Dashboard), und 60 Sekunden nach dem letzten Logout weitermacht. Aufträge kommen am einfachsten über den Pregen-Rechner im Dashboard („Plan senden“) in die Warteschlange `/var/lib/mc-dashboard/pregen-queue.json`, immer eine Dimension nach der anderen.

## Backups

| Was | Wann | Wo | Aufbewahrung |
|---|---|---|---|
| Simple Backups (komplette Welt) | alle 4 Stunden, solange Spieler online sind | erst auf dem Server, dann Google Drive | |
| Tägliches Backup | jeden Tag um 04:00, auch ohne Spieler | erst auf dem Server, dann Google Drive | |
| Upload | alle 10 Minuten prüft `mc-backup-cloud`, ob ein fertiges Backup da ist | Google Drive: `Minecraft Modpack - Void & Draconic/Backups` | 8 Tage |

**Nur noch in der Cloud:** Jedes Backup wird hochgeladen und erst gelöscht, wenn es in Google Drive nachweislich heil ist:

1. Die ZIP ist fertig geschrieben (kein Prozess hat sie mehr offen, seit 60 Sekunden unverändert).
2. Die ZIP wird komplett gelesen und jeder Eintrag per CRC geprüft, dabei entsteht die MD5-Prüfsumme.
3. Upload nach Google Drive.
4. Größe und MD5 in Google Drive müssen exakt mit der lokalen Datei übereinstimmen.
5. Erst dann wird die Datei auf dem Server gelöscht.

Scheitert ein Schritt, bleibt die Datei auf dem Server und der nächste Lauf versucht es erneut. Fehler zeigt das Dashboard unter „Backups“. Die Größe eines Backups wächst mit der Welt (Upload rund 60 MB/s).

**Zurückspielen** (Beispiel mit einem Backup von 04:00):

```bash
mc stop
cd /opt/void-draconic
rclone copy "gdrive:Minecraft Modpack - Void & Draconic/Backups/world_2026-10-09_04-00-01.zip" /tmp/
mv world world-defekt
sudo -u minecraft unzip -q /tmp/world_2026-10-09_04-00-01.zip
mc start
```

Welche Backups es gibt: `rclone lsl "gdrive:Minecraft Modpack - Void & Draconic/Backups"`. Nach dem Zurückspielen `world-defekt` und die ZIP in `/tmp` löschen, wenn alles passt.

## Bedienung

| Befehl | Wirkung |
|---|---|
| `mc start` / `mc stop` / `mc restart` | Server starten, stoppen, neu starten. Nach einem Absturz startet er von selbst neu. |
| `mc log` | laufendes Log (beenden mit Strg+C) |
| `mc console` | Server-Konsole (verlassen mit Strg+B, dann D) |
| `mc cmd "whitelist add Name"` | einen Befehl an den Server schicken |
| `mc cmd "forge tps"` | Leistung je Dimension, Ziel: 20 TPS |
| `systemctl start mc-backup-cloud` | sofort ein Backup anlegen, hochladen, prüfen und lokal löschen |
| `mc-backup-cloud` | nur fertige Backups hochladen und prüfen (läuft sonst alle 10 Minuten von selbst) |

Das Dashboard hat eine eigene Login-Seite mit „Angemeldet bleiben“ (30 Tage). Der Browser kann die Zugangsdaten speichern, abmelden geht oben rechts. Nach 5 falschen Versuchen ist die Anmeldung von dieser Adresse 5 Minuten gesperrt.

Das Dashboard zeigt live Spieler, TPS, CPU, RAM, Ereignisse, Vorgenerierung, Backups und Bestenlisten. Die zweite Zeile der Serverbeschreibung (MOTD) wird ebenfalls live aktualisiert.

## Zugangsdaten trägt Stefan selbst ein

Claude liest und tippt keine Passwörter oder Tokens. Diese Befehle fragen sie verdeckt ab:

| Wofür | Befehl auf dem Server |
|---|---|
| DuckDNS-Token | `nano /etc/void-draconic/duckdns.env`, Token bei `DUCKDNS_TOKEN=` eintragen, testen mit `duckdns-update` |
| Google Drive | am PC `rclone authorize "drive"` ausführen und bei Google anmelden, dann auf dem Server `gdrive-token` und die komplette Ausgabe einfügen |
| Dashboard-Login | `dashboard-passwort` (danach müssen sich alle neu anmelden) |

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

- Java 17, Forge 47.4.26 und das Pack von GitHub (geladen über den genauen Commit, damit nie eine veraltete Version kommt)
- 16 GB RAM mit optimierten Java-Optionen, RCON nur lokal, `sync-chunk-writes=false`
- Whitelist und OP für stman476, MarkMero und Prexynation (änderbar mit `PLAYERS="..."`)
- Dienst `void-draconic`, der beim Hochfahren und nach Abstürzen neu startet und vorher das Pack aktualisiert
- Backups: tägliches Backup um 04:00, jedes Backup geprüft nach Google Drive und danach lokal gelöscht, DuckDNS-Update alle 5 Minuten
- Dashboard mit Caddy (automatisches HTTPS), eigener Login-Seite (`mc-dashboard-auth`) und Datensammler `mc-dashboard`
- Firewall: 22 (SSH), 25565/tcp (Minecraft), 24454/udp (Voice Chat), 80 und 443 (Dashboard)
- die Befehle `mc`, `gdrive-token`, `dashboard-passwort`, `duckdns-update`

Danach die drei Zugangsdaten eintragen (siehe oben), mit `mc start` starten und die Welt aus dem letzten Drive-Backup zurückspielen. Das Skript kann gefahrlos erneut laufen: Welt, Whitelist, Zugangsdaten und Backups bleiben erhalten.

Weitere Optionen: `RAM_GB=12`, `DUCKDNS_DOMAIN=anderer-name`, `SKIP_DASHBOARD=1`, `SKIP_FIREWALL=1`, `SKIP_SYSTEMD=1`.
