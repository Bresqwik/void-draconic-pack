# Void & Draconic

Privates Modpack für Minecraft **1.21.1** mit **NeoForge**, im Stil von Valhelsia. Im Kern stecken Mekanism, Industrial Foregoing, AE2, Draconic Evolution und Void Miners.

Dieses Repo enthält nur das [packwiz](https://packwiz.infra.link/)-Verzeichnis: Links zu den Mods mit Prüfsummen und die Konfigurationen. Mod-Dateien liegen hier nicht. Sie werden direkt von Modrinth und CurseForge geladen.

## Installation mit Prism Launcher (Auto-Update)

1. In Prism eine neue Instanz anlegen: Minecraft **1.21.1** mit NeoForge **21.1.252**.
2. [packwiz-installer-bootstrap.jar](https://github.com/packwiz/packwiz-installer-bootstrap/releases) herunterladen und in den Ordner `minecraft` der Instanz legen (Instanz → *Ordner öffnen*).
3. Instanz bearbeiten → *Einstellungen* → *Eigene Befehle* aktivieren. Bei *Befehl vor dem Start* eintragen:

   ```
   "$INST_JAVA" -jar packwiz-installer-bootstrap.jar https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/pack.toml
   ```

4. Starten. Beim ersten Mal werden alle Mods geladen, danach bei jedem Start nur noch die Änderungen.

## Server

```
java -jar packwiz-installer-bootstrap.jar -g -s server https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/pack.toml
```

Das lädt alle Mods außer den reinen Client-Mods und alle Configs in den aktuellen Ordner. Danach den Server wie gewohnt starten.
