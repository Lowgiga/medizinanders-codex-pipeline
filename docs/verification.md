# Verifikation — 2026-10-03

Dieser Bericht beschreibt tatsächlich ausgeführte technische Prüfungen. Er ist
keine Betriebs-, Fach-, Produktions- oder Veröffentlichungsfreigabe.

## Abschließende automatisierte Tests

```bash
python3 -m unittest discover -s tests -v
```

Ergebnis: **183 Tests bestanden, 16,345 Sekunden, keine Fehler, keine übersprungenen
Tests**. Die getrennte unabhängige Gegenprüfung meldete ebenfalls 183 bestandene
Tests. Die Suite prüft Schemas, Claimbindungen, Szenen, Untertitel, reale
FFmpeg-Testdateien, Workergrenzen, Gates, Freeze-Manipulationen, Ersatzexporte,
Handoffänderungen, Publikationsrückmeldungen und Analytics.

Der finale Lauf erfolgte in einer neu angelegten virtuellen Pythonumgebung nach
Installation mit `python -m pip install -r requirements-lock.txt -e .`.
`python -m pip check` meldete keine verletzten Abhängigkeiten. Die vorherige
Gegenprüfung in derselben frischen Umgebung bestand ebenfalls alle 183 Tests.

Der vollständige Gate-Pfad bis A12 wird mit ausdrücklich synthetischen
Testcallbacks und Messadaptern geprüft. Das beweist die Steuerungslogik, keinen
realen Render, Fachreview, Upload oder menschlichen Kontrollvorgang.

## Vollständiger synthetischer Dry Run

```bash
ma --home /workspace/scratch/ma-release-demo demo --with-video
```

Ergebnis: **DEMO bestanden; echte Freigaben/Uploads: 0**.

Alle A01–A07 tragen `beispiel: true`. G0, G1, G2 und G3 wurden ausschließlich
als `DEMO_SIMULATION` gesetzt. Die Quellen sind tatsächlich vorhandene,
vollständig erfundene lokale Texte und eine eigene einfache SVG-Grafik; es wurde
keine externe Quelle behauptet. Die redaktionellen Outputs stammen in diesem
reproduzierbaren Dry Run aus offen deklarierten `result.json`-Fixtures.

Der Lauf prüft die Rechercheblockade vor G1, immutable Entwürfe und erste
1.0.0-Fassungen, Claim-/Satzbindungen, 106 Wörter, exakte 58-Sekunden-Timeline,
eine CTA, Disclaimer, Preflight, Freeze r001 und alle acht InVideo-Handoffdateien.
Ohne Video endet er am manuellen InVideo-Handoff. Mit `--with-video` erzeugt
FFmpeg echte 58-Sekunden-Testbytes mit sichtbarem DEMO-Label und absichtlich
falscher Auflösung 320 × 568; die technische Prüfung meldet den Fehler korrekt.
Der Lauf endet an **WAITING_FOR_HUMAN / G4**. G4, G5a und G5b bleiben ungesetzt.

Die generierten Projektdateien und der ausführliche Laufbericht liegen im
ignorierten DEMO-Ausgabebereich; sie werden nicht in Git aufgenommen. Ein neuer
Lauf erzeugt eine eigene Ausgabe und überschreibt keinen vorherigen Freeze.

## Tatsächlicher nativer Worker

Zusätzlich wurde ein verfügbarer nativer Codex-Subagent mit `fork_turns: none`
gestartet. Er erhielt ausschließlich den registrierten GAMMA-Ordner mit
Rollenprompt, TASK.json, Schemas, Themenbrief und Kanalregeln. Er erzeugte
selbst `result.json`; der echte Workerimport prüfte Eingabehashes und Schema und
importierte **A01 v0.1.0**. `Pipeline.step()` meldete anschließend
**WAITING_FOR_HUMAN / G1**. Auch dieses Projekt war ausdrücklich DEMO; G1 wurde
dabei nicht gesetzt.

Die getrennt vorhandene Codex CLI `0.159.0-alpha.3` scheiterte bei einem echten
`codex exec`-Aufruf an HTTP 401. Ihre Existenz oder ein angezeigter Login wird
daher nicht als funktionierende Anmeldung oder Webrecherche ausgewiesen.

## Weitere Prüfungen

```bash
python3 scripts/check_repository.py
python3 -m compileall -q src
```

Die Repositoryprüfung fand keine erkannten Schlüssel oder Produktionsdateien;
der Pythoncode ließ sich vollständig kompilieren. Die `.gitignore`-Gegenprobe
erfasste auch verschachtelte Quellen-, Workerlog-, Review- und Artefaktpfade.
Eine echte Montserrat-Bold-Datei wurde außerhalb des Repos zur Pixelgegenprobe
verwendet: 28 breite W überschreiten die zulässige Breite; 28 schmale i bestehen.
Die Schrift wird weder als vorhanden beim Betreiber vorausgesetzt noch committed.

Die unabhängige Befundliste und konkrete adversariale Gegenproben stehen im
[Red-Team-Bericht](red-team-review.md); die integrative Bewertung im
[Architekturreview](architecture-review.md).
