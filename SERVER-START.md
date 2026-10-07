# Server-Start – Plan für den neuen Server

Der alte Server ist seit dem 07.10.2026 weg. Pack, Client und Skripte sind fertig. Sobald ein neuer Server da ist, läuft Minecraft nach etwa 20 Minuten.

## 1. Server aussuchen

**Lehre vom alten Server:** Ein Xeon mit 2,0–2,6 GHz hat die Welt nur mit 5–6 Chunks pro Sekunde erzeugt. Beim Erkunden hat das deutlich gehakt. Für Modpacks zählt vor allem der **Takt pro Kern**, nicht die Zahl der Kerne.

| Bereich | Minimum | Empfohlen |
|---|---|---|
| Prozessor | 4 Kerne, Boost ab 4,5 GHz | 6+ Kerne, aktuelle Ryzen-Generation (7000/9000), dedizierte Kerne |
| RAM | 16 GB | 24–32 GB (12 GB für Minecraft, Rest für System und Backups) |
| Speicher | 60 GB NVMe | 100–200 GB NVMe |
| System | Debian 12 oder Ubuntu 24.04 | Debian 12 |
| Netz | öffentliche IPv4 | 25+ Mbit/s Upload |

**Vor der Bestellung:**
- Preise und CPU-Modell beim Anbieter prüfen. „vCPU“ ohne Angabe von Modell und Takt ist meist ein langsamer Server-Prozessor.
- Wenn der Anbieter beim Bestellen nach einem SSH-Schlüssel fragt, diesen eintragen. Dann kann Claude den Server direkt einrichten:

  ```
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAV3VTWbgrcZJoFb2BZ2aMuEjI317v6KUV2YPnp++XK5 stefan@DESKTOP-EO3LRT5
  ```

**Mit oder ohne Panel?**
- **Nur Minecraft:** ohne Panel. Das Setup-Skript unten richtet alles ein, gesteuert wird mit `mc start`, `mc stop` und `mc console`.
- **Auch wieder ARK:** Pelican Panel, so wie auf dem alten Server. Der Ablauf dort ist erprobt: NeoForge-Egg importieren, Server mit `bash start-pelican.sh` als Startbefehl, 16 GB Container-RAM.

## 2. Einrichtung (ohne Panel)

Ein Befehl als root auf dem neuen Server:

```bash
curl -fsSL https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/server/setup-linux.sh -o setup-linux.sh && ACCEPT_EULA=yes bash setup-linux.sh
```

Das Skript [`server/setup-linux.sh`](server/setup-linux.sh) erledigt:

- Java 21 (Eclipse Temurin) und NeoForge 21.1.252 installieren
- das Pack direkt von GitHub laden, nur die Server-Mods
- 12 GB RAM mit optimierten Java-Optionen einstellen
- Whitelist und OP für **stman476** und **MarkMero** eintragen
- einen Dienst anlegen, der Minecraft beim Hochfahren und nach einem Absturz neu startet. Vor jedem Start holt er die neueste Pack-Version.
- die Firewall öffnen: 22 (SSH), 25565/tcp (Minecraft), 24454/udp (Voice Chat)
- den Befehl `mc` anlegen: `mc start`, `mc stop`, `mc log`, `mc console`, `mc cmd "whitelist add Name"`

`ACCEPT_EULA=yes` heißt: Ihr stimmt der [Minecraft-EULA](https://aka.ms/MinecraftEULA) zu. Ohne Zustimmung startet der Server nicht.

## 3. Checkliste nach dem ersten Start

- [ ] **Adresse:** Unter [duckdns.org](https://www.duckdns.org) `meroark.duckdns.org` auf die neue IP setzen oder einen neuen Namen anlegen
- [ ] **Beitreten:** beide Spieler testen
- [ ] **Voice Chat:** im Spiel Taste `V` und gegenseitig hören (UDP 24454)
- [ ] **Welt vorgenerieren** (läuft im Hintergrund, Dauer je nach Prozessor):
  - Oberwelt: `mc cmd "chunky radius 2000"`, dann `mc cmd "chunky start"`
  - danach Nether: `chunky world minecraft:the_nether`, `chunky radius 1000`, `chunky start`
  - danach End: `chunky world minecraft:the_end`, `chunky radius 1000`, `chunky start`
- [ ] **Farmen offline:** FTB Chunks hält Chunks standardmäßig nur geladen, solange jemand online ist. Für Farmen rund um die Uhr in `world/serverconfig/ftbchunks-world.snbt` `force_load_mode: "always"` setzen (25 Chunks pro Spieler).
- [ ] **Backups:** Simple Backups behält die letzten 3 Sicherungen, aber auf demselben Server. Zusätzlich regelmäßig nach außen kopieren, zum Beispiel per geplanter Aufgabe auf Stefans PC oder NAS.
- [ ] **Leistung prüfen:** `mc cmd "spark tps"`. Ziel sind 20 TPS und unter 50 ms pro Tick.
- [ ] **MarkMero:** Prism-Instanz über den [Import-Link](README.md#installation) einrichten

## 4. Offene Entscheidungen

| Frage | Optionen |
|---|---|
| Welcher Server? | Mietserver mit schneller CPU, Heimserver oder Minecraft-Hoster mit Panel |
| Panel? | ohne (nur Minecraft) oder Pelican (auch ARK) |
| Farmen offline? | `force_load_mode` „always“ oder nur wenn jemand online ist |
| Wohin die Backups? | Stefans PC, NAS oder Cloud-Speicher |
| Adresse? | `meroark.duckdns.org` weiterverwenden oder neuer Name |

## 5. Schon fertig

- Modpack 0.2.3 mit 220 Mods, Auto-Update über GitHub
- Prism-Instanz zum Importieren mit einem Link
- Server-Paket mit Auto-Update (`Void-Draconic-Server-0.2.2.zip`, holt beim ersten Start alles auf 0.2.3)
- Server-Icons und wechselnde Beschreibung (MiniMOTD), Noisium für schnellere Weltgenerierung
- Setup-Skript für einen neuen Linux-Server
