# Architektur

Die V1 ist eine lokale Python-3.11+-CLI (`ma`) ohne Server und ohne eigenen
OpenAI-API-Client. Sie koordiniert journalistische JSON-Artefakte, unabhängige native
Codex-Worker, konkrete Operatorentscheidungen und lokale Medienprüfungen.
`IMPLEMENTATION_CONTRACT.md` definiert Felder, Abhängigkeiten und Schnittstellen;
JSON Schema Draft 2020-12 prüft die Struktur, semantische Validatoren prüfen die
Verknüpfungen. YAML wird für Konfiguration und Vorlagen verwendet.

## Zuständigkeiten

| Rolle | Ergebnis | Explizite redaktionelle Inputs |
|---|---|---|
| GAMMA | A01 Themen- und Produktionsbrief | `inputs/brief.json` |
| RESEARCH | A02 Quellenakte | A01 |
| ALPHA | A03 Claims, Faktenmatrix und Risiken | A01, A02 und zugehörige Quellensnapshots |
| BETA | A04 Dramaturgie, A05 Skript, A06 Szenen/Assets | A03; für A05 zusätzlich A04, für A06 zusätzlich A04 und A05 innerhalb desselben Ergebnisses |
| QA-RED-TEAM | A07 Preflight | A01–A06 und zugehörige Quellensnapshots |
| ORCHESTRATOR | State, Importe, Bindungen, Handoff, A08–A12 und Gateverwaltung | Die jeweils vertraglich gebundenen Inputs und konkrete Operatornachweise |

A10 entsteht aus technischen Reports und menschlichen Medienprüfungen beim
Orchestrator. A07 ist die Ausgabe des QA-Workers. Ein Agent kann medizinische oder
rechtliche Fragen aufbereiten, aber keine fachliche Freigabe ersetzen.

## Frische Worker

Jeder Lauf erhält `project/workers/ROLE/<uuid>/` mit einer eigenen `AGENTS.md`
(nur der Rollenprompt), `IMPLEMENTATION_CONTRACT.md`, passenden Dateien unter
`schemas/`, expliziten Kopien unter `inputs/` und bei Bedarf `sources/`.
Beispielsweise heißen Vorgängerkopien `inputs/A01.json` und `inputs/A02.json`.
Quellensnapshots werden nur den Rollen mit Quellenprüfung gegeben: RESEARCH,
ALPHA und QA-RED-TEAM. Der authoritative Quellenspeicher liegt unter
`project/sources/`.

Der Orchestrator prüft die tatsächlich installierte CLI und ihre Fähigkeiten und
startet einen frischen Prozess mit `codex exec --ephemeral --ignore-user-config -C`
auf diesem Verzeichnis. Seine Umgebung wird bereinigt; Systemcredentials werden
nicht in Prompts übergeben. Eine fehlende Option oder native Laufzeit ist ein
sichtbarer Blocker, kein Anlass für einen stillen Wechsel zu einem eigenen API-Client.

Importierbar ist ausschließlich `result.json` mit der Form
`{"artifacts": [...]}`. BETA liefert genau A04, A05 und A06; jeder andere
redaktionelle Worker genau sein Artefakt. Ein erster Entwurf hat Version `0.1.0`
und Status `Entwurf`. Die äußeren Eingabebindungen setzt der Orchestrator aus den
tatsächlich verwendeten Artefaktversionen und SHA-256-Werten. Worker setzen keine
Gates und verändern keine Vorgänger oder Projektdateien außerhalb ihres Auftrags.

Die Eingabetrennung begrenzt erlaubten Kontext. Sie ist keine Betriebssystem-
Sandbox: Ein lokaler Prozess kann unter seinen OS-Rechten weiterhin andere Dateien
lesen. Eine harte Read-Isolation würde eine zusätzliche Sandbox verlangen.

## Speicherung und Nachweise

Artefakte sind unveränderlich unter `artifacts/Axx/vVERSION.json` gespeichert.
`state.json.current[Axx]` bindet `version`, `path` und `sha256`. Eingaben jedes
Artefakts referenzieren konkrete Vorgängerversionen und Hashes. Ein neuer Import
macht abhängige Ergebnisse und Freigaben bei veränderten Bindungen veraltet.
`ma invalidate` erfasst Änderungen und den notwendigen Rückweg ausdrücklich.

Ein Zugriffsfeld, ein gesetztes `original_geoeffnet` oder ein Hashstring allein
beweist keine Provenienz. Der Hash muss auf vorhandene Originalbytes passen;
Fundstelle und Originalöffnung müssen tatsächlich nachvollziehbar sein. Fachliche
Bewertung, Rechteklärung und Operatoratteste sind getrennte Nachweise. Die V1
behauptet keine eigenständige kryptografische Identität oder geprüfte C2PA-Kette.

Projekt- und Produktionsdaten liegen standardmäßig außerhalb des Repositorys.
Private Arbeitslogs werden nicht als Produktionsartefakte oder Quellenbeweise
importiert. Demoartefakte tragen `beispiel: true`; simulierte Gates tragen
`DEMO_SIMULATION` und können keine Produktionsfreigabe begründen.

## Zentrale Schnittstellen

- `validate_artifact(data, artifacts=None, production=False) -> list[str]`
- `validate_bundle(artifacts, production=False) -> list[str]`
- `inspect_video(path, report_dir) -> dict`
- `validate_srt(path, font_path=None) -> dict`
- `generate_srt(A05_inhalt, A06_inhalt) -> str`

Validierung verändert keine Eingaben. Medienchecks berichten `bestanden`,
`fehlgeschlagen` oder `nicht_geprueft`; unmessbare Werte werden nicht erfunden.
Ein bestandener Containercheck ersetzt weder Hör- und Sichtprüfung noch die
Prüfung des tatsächlich verarbeiteten privaten YouTube-Videos.
