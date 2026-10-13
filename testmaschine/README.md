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
