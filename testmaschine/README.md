# Testmaschine (Windows ↔ Mac)

Tests laufen immer auf dem Rechner, an dem Stefan **nicht** spielt, und immer mit dem Konto **MarkMero**.
So bleibt `stman476` frei für den Server.

| Stefan ist … | spielt auf | Test läuft auf |
|---|---|---|
| zuhause | Windows-PC (stman476) | MacBook (MarkMero) |
| unterwegs | MacBook (stman476) | Windows-PC (MarkMero) |

Erkennung: Läuft auf dem Windows-PC die Spiel-Instanz `Void-Draconic-1.20.1` oder sagt Stefan „bin zuhause“ → Mac testet.
Sonst testet der Windows-PC selbst.

## Zwei Instanzen pro Rechner

- `Void-Draconic-1.20.1` – Spiel-Instanz, Konto stman476, PreLaunch zieht `main`.
- `Void-Draconic-Test` – Test-Instanz, Konto MarkMero, **kein** PreLaunch. Stand kommt per Skript aus einem Branch.

Start der Test-Instanz:

- Windows: `powershell -ExecutionPolicy Bypass -File vd-test.ps1 -Branch test`
- Mac: einmalig `bash setup-mac.sh` (legt die Instanz an, Prism holt Java und vor jedem Start per PreLaunch den Branch `test`), danach `NOSYNC=1 ./vd-test.sh test Sandbox`

`--profile MarkMero` wählt das Konto nur für diesen Start, das Standard-Konto in Prism bleibt stman476.

## Ablauf eines Tests

1. Änderung bauen, auf Branch `test` pushen (nie direkt auf `main`).
2. Testmaschine: `vd-test` holt `test` per packwiz und startet in die Welt `Sandbox`.
3. Log prüfen (Mixins, Fehler, Crash), im Spiel testen, Ergebnis zurückmelden.
4. Erst nach erfolgreichem Test: Merge nach `mc1.20.1` und `main`.

## Verbindung zwischen den Rechnern

Beide Rechner haben die Claude-App mit demselben Konto und **Remote Control** an.
Auf jedem Rechner bleibt eine Sitzung offen, die als Testmaschine dient:

- `Mac Testmaschine` (auf dem MacBook)
- `Windows Testmaschine` (auf dem PC, wenn Stefan unterwegs ist)

Die Haupt-Sitzung schickt den Auftrag per Nachricht an die Testmaschine. Die Testmaschine meldet das Ergebnis zurück.

## Einmalig einrichten (pro Rechner)

1. Prism Launcher installieren. Die Konten **stman476** und **MarkMero** meldet Stefan selbst an. Standard bleibt stman476.
2. Spiel-Instanz importieren (packwiz, Branch `main`).
3. Test-Instanz anlegen: Spiel-Instanz in Prism kopieren → Name `Void-Draconic-Test` (Ordnername genau so), PreLaunch-Befehl aus, RAM 10 GB.
4. In der Test-Instanz eine Welt `Sandbox` anlegen (Kreativ, Cheats an).
5. Claude-App: Remote Control an, Ruhezustand aus (Windows: Energieoptionen; Mac: „Ruhezustand verhindern“ in der App).
6. Für Tests im Spiel: der Claude-App die Bildschirmsteuerung erlauben (Mac: Bedienungshilfen + Bildschirmaufnahme).

## Ablauf vor jedem Test (für Claude, Stefans Vorgabe 14.10.2026)

Geräte: **Windows-PC** (stärker, Stefans Haupt-Spielrechner, Sitzung „Minecraft Modpack“) und **MacBook** (Sitzung „Minecraft Modpack auf Macbook“). Die Sitzungen erreichen sich per SendMessage.

1. **Prüfen:** Wer ist auf dem Server (`rc.py list`)? Auf welchem Gerät läuft Minecraft, und welches ist mit 193.111.248.12:25565 verbunden?
   - Windows: `Get-NetTCPConnection -RemoteAddress 193.111.248.12 -State Established`, javaw-Kommandozeile (`Void-Draconic-1.20.1` = Spiel, `Void-Draconic-Test` = Test)
   - Mac: `pgrep -fl "instances/Void-Draconic"`, `lsof -nP -iTCP@193.111.248.12:25565 -sTCP:ESTABLISHED`
2. **Gerät wählen:** das Gerät, das **nicht** mit dem Server verbunden ist. Spielt Stefan nirgends: MacBook. Nie Spiel-Instanz oder stman476, immer MarkMero.
3. **Vorher ansagen:** Gerät + Grund, automatische Tests, Tests mit Stefans Eingabe, ungefähre Dauer.
4. **Reihenfolge:** erst alle automatischen Prüfungen (Laden, Log, Mixins, Crash), Tests mit Stefans Eingabe zuletzt (oder parallel).
5. **Ergebnis** als ✅/❌-Liste, bei ❌ mit Logzeilen. Test-Instanz danach schließen, wenn sie nicht mehr gebraucht wird.
