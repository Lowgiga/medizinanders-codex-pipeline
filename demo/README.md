# Synthetische DEMO

```bash
ma --home /tmp/medizinanders-probelauf demo
ma --home /tmp/medizinanders-probelauf demo --with-video
```

Die Demo beschreibt einen erfundenen Papierstern in einem erfundenen Archiv.
Sie verwendet keine Patientenangaben, medizinischen Aussagen oder echten
Sammlungsdaten. Alle Artefakte tragen `beispiel: true`; alle Entscheidungen
tragen `kind: DEMO_SIMULATION`. G0 bis G3 werden ausschließlich innerhalb
dieser Demo simuliert. Eine produktive Freigabe entsteht dadurch nicht.

Der ausführbare Projektordner liegt unter
`MA_HOME/demo/projects/MA-YYYYMMDD-NNN/`. Die produktive Betreiberkonfiguration
und produktives G0 bleiben erhalten. `demo --output BASIS` wählt einen anderen
Basisspeicher; das Demoprojekt liegt dann unter `BASIS/demo/projects/`.
Der Basisspeicher muss außerhalb des Repositorys liegen.

Ein neuer, zum Lesen bestimmter Snapshot entsteht unter
`demo/output/MA-YYYYMMDD-NNN-<kennung>/`. Die CLI gibt den Pfad seines
`REPORT.md` aus. Dieser Bericht nennt die tatsächlich ausgeführten Prüfungen,
die simulierten Gates und den erreichten Wartezustand. `DEMO_RESULT.json`
enthält die bereinigte Ergebnisübersicht. Der gesamte Output ist gitignoriert.
Er enthält ausschließlich synthetische Daten; Maschinenpfade werden
neutralisiert und private Workerlogs werden nicht kopiert.

| Rolle | Fixture-Ergebnis |
| --- | --- |
| GAMMA | A01: synthetischer Themenauftrag |
| RESEARCH | A02: lokales erfundenes Original mit echter Fundstelle und Byte-Hash |
| ALPHA | A03: ein bestätigter Claim über den Inhalt dieser fiktiven Quelle |
| BETA | A04–A06: Zeitplan, Sprechertext, Szenen, eigene Grafik und InVideo-Prompt |
| QA-RED-TEAM | A07: sieben Pflichtprüfungen mit konkretem DEMO-Nachweis |

Die Rollen werden durch lokale `result.json`-Fixtures vertreten. Dieser
Probelauf startet keine nativen Codex-Worker. Die Importe, Abhängigkeiten,
Versionierung, Gateblockaden, semantischen Prüfungen und Freeze-Erstellung
durchlaufen den tatsächlichen Orchestrator. Ein A02-Import vor G1 wird
probeweise versucht und muss scheitern. Die ursprünglichen Fassungen bleiben
unverändert erhalten.

`sources/demo_original.txt` wird lokal erzeugt, geöffnet und aus seinen
tatsächlichen UTF-8-Bytes gehasht. `https://example.invalid/DEMO/papierstern`
ist ausdrücklich eine Beispieladresse und wird nicht abgerufen. Der Claim
`C-DEMO-001` belegt nur, dass der Papierstern-Satz in dieser erfundenen Quelle
steht. Er behauptet keinen realen Archivfund. Die Grafik besteht aus eigenen
SVG-Formen; der lokale Eigenherstellungsnachweis liegt neben dem Original.

Der Sprechertext hat 106 Wörter und endet bei 54 Sekunden. Der feste Disclaimer
erscheint separat und stumm auf Schwarz von 54 bis 58 Sekunden. Es gibt genau
eine CTA. Alle faktischen Texte binden den Quellenclaim. Der Handoff enthält
den vollständigen Text, Szenen, Profilwerte, Quellen, Rechtehinweise und
unausgefüllte menschliche Checklisten. `DEMO_ESTIMATED.srt` erfüllt die messbaren
Text- und Zeitregeln; ihre Synchronität zu tatsächlicher Sprache, die
Montserrat-Bold-Pixelbreite und eingebrannte Darstellung bleiben offen.

Der gewöhnliche Lauf endet bei `WAITING_FOR_HUMAN / G3_INVIDEO`: Ein echter
manueller InVideo-Render steht noch aus. G4, G5a und G5b werden probeweise
angefordert und müssen ohne reale Nachweise blockieren. Die Demo führt keinen
Upload und keine Veröffentlichung aus.

Mit `--with-video` werden tatsächlich installiertes `ffmpeg` und `ffprobe`
verwendet. ffmpeg erzeugt eine sichtbar mit DEMO markierte 58-Sekunden-Datei
in **320 × 568 Pixeln**, damit die echte technische Auflösungsprüfung
`fehlgeschlagen` meldet. Diese Datei ist ein Negativtest. A08 bindet die
vorhandenen Bytes mit `render_real: false`; ein InVideo-Render wird nicht
bestätigt. Der Lauf endet dann bei G4 mit negativem QA-Ergebnis und ohne
G4-/G5-Freigaben, Finaldatei oder Plattformnachweis.

Die Python-Schnittstellen sind `fixtures(project_id)`,
`prepare_sources(project_path)` und `run_demo(home, repo, with_video=False)`.
Die Demo-Tests prüfen den vollständigen normalen Lauf und, bei vorhandenen
Medienwerkzeugen, den echten negativen Videotest:

```bash
python -m unittest discover -s tests -p test_demo.py -v
```
