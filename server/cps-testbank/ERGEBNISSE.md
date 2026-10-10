# CPS-Testbank – Ergebnisse vom 10.10.2026

Ziel: Die Vorgenerierung (Pregen) auf dem Live-Server deutlich schneller machen, ideal mit einer Aufteilung von
8 Kernen für die Weltgenerierung und 4 Kernen für Spieler. Getestet auf dem Tube-Hosting-Server
(AMD EPYC 7542, 12 vCPUs, 31 GB RAM) mit einer Kopie des Live-Packs 0.5.7 und dem Seed der Live-Welt.

## Aufbau der Tests

- Testserver: `/opt/vd-cps-test`, Kopie des Live-Servers ohne Welt, eigene Ports, Java 17, 9–12 GB Heap.
- Messung: Chunky, Quadrat um Block 20 000 / 20 000 (frisches Gelände), Radius 400 Blöcke = 2 601 Chunks.
  Chunks/s = 2 601 ÷ Gesamtzeit laut Chunky. MSPT alle 15 s per `forge tps`.
- Jede Variante bekam eine Kopie derselben Startwelt (nur Spawn generiert), damit nur die gemessene Fläche neu ist.
- Profil: Java Flight Recorder während der Baseline, ausgewertet mit `jfr-top.py`.
- Skripte: `vd-bench.py`, `vd-rcon.py`, `vd-langtest.sh`, `jfr-top.py` in diesem Ordner.

## Ergebnisse Oberwelt (Radius 400, 2 601 Chunks)

| Lauf | Kerne | Zeit | Chunks/s | Faktor | MSPT Ø / max |
|---|---|---|---|---|---|
| Referenz Live-Server 09.10. (ohne Starlight) | 12 | – | 4,6 | – | 3,0 |
| Baseline (Pack wie live: Noisium, Canary) | 8 (4–11) | 11:16 | **3,85** | ×1,0 | 3,0 / 6,0 |
| ByePregen 1.1.2.3 statt Noisium | 8 | 10:51 | 4,00 | ×1,04 | 2,9 / 5,9 |
| ByePregen + Fast Noise | – | – | – | – | zurückgestellt |
| C2ME-Port (Makki132), Standard | 8 | 2:09 | 20,16 | ×5,2 | 2,8 / 3,6 |
| C2ME, 8 Worldgen-Threads, alle 12 Kerne | 12 | 1:34 | 27,67 | ×7,2 | 3,6 / 4,0 |
| **C2ME, 8 Threads, Dekoration seriell (live)** | 12 | 1:46 | **24,54** | **×6,4** | 2,5 / 2,9 |

## Ergebnisse Dimensionen (C2ME, 8 Threads, alle 12 Kerne)

„Vorher“ = Vorgenerierung auf dem Live-Server ohne C2ME am 08./09.10. (Radius 1 000, andere Mitte, daher nur grob vergleichbar).

| Dimension | Radius | Chunks | Zeit | Chunks/s | vorher | Faktor | Hinweis |
|---|---|---|---|---|---|---|---|
| Oberwelt | 1 500 | 35 721 | 13:17 | 44,8 | 4,2 | ×10,7 | Dekoration noch parallel |
| Nether | 1 000 | 16 129 | 1:10 | 230,4 | 55,0 | ×4,2 | Dekoration noch parallel |
| Twilight Forest | 750 | 9 025 | 2:01 | 74,6 | 61,3 | ×1,2 | 1. Versuch Absturz, Fix: Generator seriell |
| End | 750 | 9 025 | 1:01 | 148,0 | 106,8 | ×1,4 | mit paralleler Dekoration 265 Chunks/s |
| Aether | 500 | 4 225 | 0:16 | 264,1 | 133,3 | ×2,0 | 1. Versuch Hänger (Immersive Petroleum) |
| Everbright | 500 | 4 225 | 0:25 | 169,0 | 71,4 | ×2,4 | |
| Everdawn | 500 | 4 225 | 0:22 | 192,1 | 48,0 | ×4,0 | |
| Otherside | 500 | 4 225 | 1:11 | 59,5 | 50,6 | ×1,2 | |
| Bumblezone | 500 | 4 225 | 0:50 | 84,5 | 47,2 | ×1,8 | |
| Alfheim | 500 | 4 225 | 2:56 | 24,0 | 49,6 | ×0,5 | langsamer, Mitte 0/0 – noch offen |
| The Abyss | 200 | 729 | 0:50 | 14,6 | – | – | vorher Sekunden pro Chunk |

Alle 11 Dimensionen liefen am Ende ohne Absturz und ohne Hänger.

## Was wir gelernt haben

1. **Der Engpass ist die fehlende Parallelität, nicht die Rechenzeit pro Chunk.** In der Baseline waren von 8 Kernen
   im Schnitt nur 1,3–3,5 ausgelastet. Die Tickzeit lag bei 3 ms, der Hauptthread war also nicht das Problem.
   Vanilla-Minecraft verteilt die Chunk-Aufgaben einfach nicht breit genug auf die Worker-Threads.
2. **Profil der Baseline:** ~20 % der Rechenzeit gehen in `hashCode`/`equals` von Terrain-Formeln (CubicSpline,
   Density Functions – typisch für Tectonic/Terralith), dazu Rauschfunktionen, Aquifere, Biom-Suche.
   Blueprint (Modded-Biome-Source) 6 %, YUNG's-Strukturen 6 %, Integrated API, Valhelsia, Lithostitched je ~1 %.
3. **ByePregen bringt hier praktisch nichts** (+4 %), weil es die Rechenzeit pro Chunk verkürzt, nicht die Parallelität.
   Außerdem Mixin-Konflikt mit Canary (`ServerChunkCache.getChunk`), nur lauffähig mit
   `mixin.world.chunk_access=false` in `config/canary.properties`.
4. **C2ME ist der große Hebel:** ×5 auf 8 Kernen, ×6–7 auf 12 Kernen, auf großen Flächen ×10 (die Parallelität
   wächst mit der Fläche). Die Tickzeit bleibt bei 2,5–3,6 ms, Spieler merken davon nichts.
5. **Nicht threadsichere Mods sind die Gefahr von C2ME:**
   - **Twilight Forest:** `TFCavesCarver` nutzt einen gemeinsamen Zufallsgenerator → Absturz
     „Accessing LegacyRandomSource from multiple threads“. Fix: `serializedChunkGenerators` enthält `twilightforest`.
   - **Immersive Petroleum:** `ReservoirHandler` (Ölvorkommen) schreibt in statische HashMaps →
     `ConcurrentModificationException` in der Dekorationsphase, betroffene Chunks werden nie fertig, Chunky hängt.
     Betrifft alle Dimensionen. Fix: `allowThreadedFeatures = false` (kostet nur ~12 % Tempo).
   - **Spartan Weaponry** greift beim Ausrüsten von Mobs auf den Welt-Zufall zu – C2ME fängt das selbst ab (nur Log-Warnung).
6. **Testserver nie neben dem Live-Server starten:** Ein Mod beendet den Server mit Exit-Code 1, wenn seine Ports
   belegt sind (ohne Fehlermeldung). Außerdem landen tmux-Sitzungen im cgroup des startenden Dienstes und sterben mit ihm.
7. **Chunky übernimmt gespeicherte Aufträge** aus `config/chunky/tasks` – vor einem neuen Lauf `chunky confirm` oder
   den Ordner leeren.

## Empfohlenes Setup (seit Pack 0.5.8 live)

- Mod: C2ME-Forge-Port von Makki132, `c2meforge-0.2.0-forge.9.8-all.jar` (CurseForge 1610389 / 9040801), **nur Server**.
- `config/c2me.toml`:
  - `globalExecutorParallelism = 8` (8 Kerne Weltgenerierung, 4 frei für Server und Spieler)
  - `allowThreadedFeatures = false` (Immersive Petroleum)
  - `serializedChunkGenerators = "fr.meulti.mbackrooms,twilightforest"`
- Noisium, Canary, ModernFix, Structure Layout Optimizer bleiben.
- Hochrechnung für die Oberwelt (Quadrat um 0/0) bei ~25–45 Chunks/s: Radius 5 000 ≈ 2,5–4,5 Std.,
  Radius 10 000 ≈ 10–17 Std., Radius 15 000 ≈ 22–39 Std. (ohne C2ME: 10,6 Tage für Radius 15 000).

## Offene Punkte

- Alfheim war mit C2ME langsamer als vorher. Ursache noch nicht untersucht (kleine Dimension, spätes Spiel).
- Test „C2ME + Fast Noise statt Noisium“ wurde nicht gemacht.
- Bei neuen Worldgen-Mods immer erst auf der Testbank mit C2ME prüfen.
