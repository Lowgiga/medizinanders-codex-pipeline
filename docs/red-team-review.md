# Unabhängiger QA-/Red-Team-Review

Stand: 2026-10-03. Geprüft wurden `IMPLEMENTATION_CONTRACT.md`, `AGENTS.md`,
die A01–A12-Schemas, Orchestrator, Workerimport, CLI, Handoffs, Medien-/SRT-Prüfer,
Datenschutzregeln und die vorhandenen Tests. Der Review verändert ausschließlich
diese Datei; Produktionscode wurde durch die jeweils zuständige Implementierung
korrigiert. Es erfolgten keine Credentials-Lesezugriffe, externen Uploads oder
Veröffentlichungen.

Nach den gezielten Gegenproben sind alle elf Befunde behoben. Es verbleibt kein
offener K0-/K1-/K2-Codebefund aus diesem Review. Die operative native Anmeldung
und eine tatsächliche Produktion bleiben separat nachzuweisen.

Die isolierten Produktionszweig-Proben verwenden ausdrücklich Testcallbacks,
synthetische Dateien und deklarierte Messadapter. Sie prüfen die State-Machine
und deren Bindungen. Sie beweisen keinen InVideo-Render, keine Fachentscheidung,
Smartphoneprüfung, Kosten, Plattformverarbeitung oder Veröffentlichung.

## Befunde und Rückwege

K0 bezeichnet einen kritischen Verstoß, K1 eine blockierende Funktions- oder
Bindungslücke, K2 eine begrenzte Robustheits-/Datenschutzlücke. Die Schwere in der
Tabelle beschreibt den gefundenen Fehler vor seiner Behebung, nicht eine
Produktionsfreigabe.

| ID | Datei / Funktion | Problem | Soll | Ist der ursprünglichen Probe | Schwere | Rückweg / Stand |
|---|---|---|---|---|---|---|
| RT01 | `engine.py:_import`; `validation.py:validate_artifact` | Neue Version wurde gegen die alte eigene Bundlefassung validiert. | Neue Fassung gegen ihre tatsächlichen Vorgänger prüfen; Vorgängerfassungen bytegleich erhalten. | Jede Ersatzfassung meldete einen Bundlekonflikt; das erste Previewattest konnte A08 nicht ergänzen. | K1 | Kandidat vor der Validierung einsetzen. Behoben; Previewattest und vollständiger Gate-Testpfad funktionieren. |
| RT02 | `engine.py:_update_final_artifacts`; `validation.py:_validate_qa` | A10 verlangte ausschließlich automatisch bestandene Checks, obwohl bestimmte Pflichten nur menschlich bzw. mit Exportprotokoll nachweisbar sind. | Die fünf ausdrücklich erlaubten, hashgebundenen Ergänzungen akzeptieren und den ursprünglichen unbekannten Messstatus erhalten. Fehler dürfen nicht überstimmt werden. | Trotz vollständigem Finalattest konnte `freigabefaehig` wegen `nicht_geprueft` nicht importiert werden. | K1 | Erlaubte `human_resolutions` mit Originalreport-, Nachweis- und Attesthash prüfen. Behoben; positive Ergänzung und Fehlerblockade getestet. |
| RT03 | `engine.py:attest`, `attestation_valid` | Playbackchecks und die von der Checkliste angegebenen Medienbindungen fehlten in der Prüfung. | Alle zwölf Medienchecks plus fünf Playbackchecks verlangen; Checkliste, Freeze, Medien-/SRT-Hash und Upload-ID müssen den aktuellen Prüfgegenstand treffen. | `youtube_processing_complete=false` konnte bei zwölf lokalen Häkchen genügen; alte Formulare konnten auf neue Bytes gebunden werden. | K1 | Stage-/Hashvergleich vor Bestätigung, vollständige Playbackpflichten, `example=false`. Behoben; falscher Finalhash und unvollständige Verarbeitung unabhängig abgewiesen. |
| RT04 | `engine.py:youtube_private`, `gate_problems(G5b)` | Alter privater Upload blieb nach neuem Finalexport verwendbar; eine neue Rückmeldung scheiterte an exklusiver Datei. | Aktueller privater Upload muss A09 treffen; Ersatzupload benötigt neue Playbackprüfung und G5b. | Privater Record wurde nicht mit dem aktuellen Finalhash verglichen. | K1 | Vorherigen Record archivieren, neue konkrete Rückmeldung registrieren, Playback/G5b entfernen, Hashvergleich am Gate. Behoben; Code und Lifecycle-Regressionen geprüft. |
| RT05 | `engine.py:verify_freeze` | Die Prüfung iterierte nur die im Manifest vorhandenen Artefaktbindungen. | Exakt A01–A07, richtige Projekt-/Demo-/Revisionsbindung, vollständige Dateiliste und Hashwerte verlangen. | Manipulierte A05-Kopie mit neu berechneten Summen wurde akzeptiert, sobald A05 aus `artifact_binding` entfernt war. | K1 | Erwartete Pflichtmengen und Manifestidentität ausdrücklich vergleichen. Behoben; dieselbe adversariale Probe wird jetzt abgewiesen. |
| RT06 | `engine.py:gate_problems`, `repair_handoff` | Fehlende Handoffdateien konnten durch eine neue Gatebindung als vollständiges Paket gelten. | Acht konkrete InVideo-Inhaltsdateien und das vollständige YouTube-Paket müssen vorhanden und nichtleer sein. | Nach Löschen von `INVIDEO_PROMPT.txt` blieb `gate_problems(G3)` leer. | K1 | Pflichtdateien am Gate prüfen, deterministischen Reparaturbefehl bereitstellen. Behoben; Löschen blockiert, `repair-handoff` stellt das Paket ohne Freigabe wieder her. |
| RT07 | `validation.py`; `schemas/common.schema.json` | ISO-Datum hing an einem optionalen `date-time`-Formatprüfer. | Datum und Abruf-/Renderzeit auch in der tatsächlich installierten Abhängigkeitsumgebung prüfen. | `FormatChecker` enthielt hier keinen `date-time`-Checker; `datum="03.10.2026"` passierte. | K2 | Eigenständige ISO-Prüfung statt unbestätigter optionaler Formatfunktion. Behoben; entsprechende Tests bestehen. |
| RT08 | `engine.py:_invalidate_state` | Finaländerungen entfernten auch Previewreports und Previewatteste. | Ein Export invalidiert A09 und downstream sowie G5a/G5b; unveränderte Previewnachweise und G4 bleiben gültig. | Blanket-Löschung konnte G4 mittelbar veralten lassen. | K1 | Nachweisentwertung nach betroffener Stufe trennen. Behoben; G4, Previewreport und Previewattest bleiben nach `invalidate(export)` erhalten. |
| RT09 | `engine.py:youtube_published`, `analytics` | Ein alter Veröffentlichungsmarker legitimierte Analytics für eine neue, erst vorbereitete A11-Fassung; erneute Veröffentlichung war nicht registrierbar. | Analytics nur zum aktuellen veröffentlichten A11-/Final-/Uploadstand; neue menschliche Veröffentlichung versioniert dokumentieren. | Nach Ersatzexport war A11 `vorbereitet`, `analytics()` akzeptierte trotzdem; zweite Rückmeldung scheiterte an vorhandener `youtube-published.json`. | K1 | Publikationsrecord archivieren/ersetzen und aktuelle Publikationsbindungen vor A12 prüfen. Behoben; veralteter Marker blockiert, zweite Testpublikation wird archiviert registriert, erst danach gelingt A12. |
| RT10 | `.gitignore` | Verschachtelt in das Repo kopierte Projektunterlagen waren commitfähig. | Auch typische verschachtelte Projekt-, Quellen-, Worker-, Review- und Artefaktpfade ausschließen. | `git check-ignore` erfasste vier typische `random/projects/…`-Privatpfade nicht. Der voreingestellte externe Speicher war bereits korrekt geschützt. | K2 | Rekursive Ausschlüsse und Workerlog-/Entscheidungsregeln ergänzen. Behoben; alle vier Pfade werden jetzt ignoriert. |
| RT11 | `engine.py:gate_problems`, `binding`; abgeleitete Handoffs | Ein neuer Gateentscheid konnte einen manuell geänderten Handoff binden, ohne A05/A06/A07 zu erneuern. | Abgeleitete Produktions- und Metadatendateien müssen den validierten Artefakten entsprechen; neuer Wortlaut benötigt BETA/QA-Rückweg. | Geänderte `VOICEOVER.txt` entwertete das alte G3 korrekt, eine erneute G3-Freigabe akzeptierte sie bei unverändertem Freeze jedoch wieder. | K1 | Deterministisch erwartete Handoffbytes am Gate vergleichen; Reparatur stellt diese Bytes her. Behoben; veränderte Sprecherdatei blockiert neue G3-Bestätigung, Reparatur beseitigt den Blocker. |

## Reproduzierbare Evidenz

Abschließender unabhängiger Gesamtlauf nach den Korrekturen:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Tatsächliches Ergebnis: **183 Tests, OK, 13,527 Sekunden**. Der Zwischenstand
mit 167 Tests bestand ebenfalls. Der frühere Lauf mit 125 Tests fand zwei
Fehler: die echte ISO-Datumslücke und
eine falsche Wortzahl-Testannahme. Der verwendete Beispielsatz hat nach der
definierten Zählweise neun Wörter; zehn waren kein erforderlicher Produktwert.

Zusätzliche unabhängige Proben in temporären Verzeichnissen, ohne produktiven
Speicher und ohne Netzwerkaktionen:

- G0 → G1 → G2 → G3 → Preview-QA/Attest → G4 → Final-QA/Attest → G5a →
  private Testrückmeldung → Playbackattest → G5b war erreichbar. G4 blieb nach
  Final-QA und Finalattest gültig. Ein abweichender Finalhash wurde vor
  Bestätigung abgewiesen. `youtube_processing_complete=false` wurde abgewiesen.
- Ein neuer Finalexport entfernte G5a/G5b und erhielt G4 sowie Previewreport und
  Previewattest. Quellen-/Bedeutungs-/Wortlautrückwege und immutable Versionen
  werden zusätzlich durch `test_engine.py` geprüft.
- Der Workerimport wies einen anderen Dateinamen, fremde Ausgabe-Artefakte,
  veränderte `TASK.json`, veränderte kopierte Eingaben und eine nicht mehr
  zulässige wiederholte Rolle ab. A02 vor G1 wurde abgewiesen. Ein geprüfter
  Quellenflag ohne tatsächliche Snapshotbytes wurde abgewiesen; A02 wurde
  dabei nicht in den State aufgenommen.
- Die Freezeprobe änderte A05, aktualisierte ihre Dateihashes und entfernte
  anschließend A05 aus `manifest.artifact_binding`. Die korrigierte Prüfung
  meldet: `Freeze-Pflichtbindungen, Projekt, Revision oder DEMO-Zuordnung sind
  inkonsistent.` Eine bloße Aktualisierung der Summen ohne Entfernen der
  Bindung wird ebenfalls abgewiesen.
- Das Löschen von `INVIDEO_PROMPT.txt` meldet einen konkreten G3-Blocker und
  den Rückweg `ma repair-handoff <ID>`. Nach Reparatur war das vollständige
  Paket wieder prüfbar; der Befehl erteilte kein Gate.
- Nichtinteraktive `operator_confirmation()` wird abgewiesen. Die CLI besitzt
  keine `--yes`-Option. Die Grenze gegenüber einem absichtlich manipulierten
  vertrauenswürdigen lokalen Operator wird nicht als OS-Sicherheitsgrenze
  dargestellt.

RT09 wurde mit `ProductionMediaLifecycleTests` als isoliertem Testadapter
reproduziert: erster Testpublikationsstand, `invalidate(export)`, neue
Finalbytes und Final-QA/-Attest. Vor erneuter Veröffentlichung war
`A11.inhalt.visibility == "vorbereitet"`; ein korrekt geformter A12-Import
passierte dennoch. Nach neuem privaten Testrecord, Playback und G5b scheiterte
die zweite lokale Publikationsrückmeldung an der vorhandenen Datei.

Die identische Gegenprobe nach der Korrektur wies Analytics beim neuen
`vorbereitet`-Stand ab. Eine neue private Testrückmeldung mit erneutem Playback
und G5b erlaubte die zweite lokale Publikationsrückmeldung; das Archiv enthielt
genau den vorherigen Publikationsrecord. Erst anschließend wurde A12 akzeptiert.

RT11 wurde mit `EngineGateTests` reproduziert: `to_g3()`, anschließend
`handoff/invideo/VOICEOVER.txt` inhaltlich verändern. Das alte G3 war ungültig,
aber `gate_problems(pid, "G3")` lieferte `[]`; ein neuer Testcallbackentscheid
für G3 wurde akzeptiert. A05, A06, A07 und der Freeze blieben unverändert.

Die identische Gegenprobe nach der Korrektur meldete einen expliziten
Wortlautkonflikt mit A04–A06 und blockierte die erneute G3-Bestätigung.
`repair-handoff` stellte den geprüften Originaltext wieder her; danach war der
Blocker entfernt. Geänderter YouTube-Titel wird zusätzlich durch die Regression
`test_nonempty_modified_upload_title_cannot_add_claims_before_g5a` geprüft.

Die Git-Probe erstellt keine sensiblen Testdateien:

```sh
git check-ignore \
  random/projects/MA-20261003-001/sources/private.txt \
  random/projects/MA-20261003-001/workers/ALPHA/run/native.stdout.log \
  random/projects/MA-20261003-001/review/medical.decision.json \
  random/projects/MA-20261003-001/artifacts/A03/v1.0.0.json
```

Nach der Korrektur wurden alle vier Pfade ausgegeben.

## Tatsächliche Laufzeit und Grenzen

Der unabhängig ausgeführte `ma doctor` meldete `codex-cli 0.159.0-alpha.3`,
vorhandenes `codex exec`, native Suchoption, Git, gh, ffmpeg und ffprobe.
Er meldete ausdrücklich `cli_auth_network_tested: false`,
`invideo_automation: false` und `youtube_automation: false`. Diese Aussagen
sind keine erfolgreiche Anmeldung oder funktionierende Webrecherche.

Die Implementierung meldete separat einen realen nativen Authentifizierungsstopp
mit HTTP 401. Dieser Review hat ihn nicht durch Credentialszugriff oder einen
erneuten Loginversuch reproduziert. Der native Produktionslauf ist deshalb
operativ noch nicht nachgewiesen. `run/resume --prepare-only` und die minimale
Dateiübergabe stehen bereit; ein API-Fallback wird nicht behauptet. Der
401-Unit-Test ist ausdrücklich synthetisch und kein zusätzlicher Loginbeleg.

Originalöffnung, Rechte, Fachqualifikation, tatsächliche Smartphoneprüfung,
Renderherkunft und Plattformplayback benötigen weiterhin die dokumentierten
realen Handlungen. Hashes beweisen die Bindung an vorhandene Bytes, nicht deren
wissenschaftliche Wahrheit, Rechte oder Herkunft. Die Prüfung behauptet keine
C2PA-Verifikation und keine OS-Isolation der lokal lesbaren Dateien.

Ein Testpass ersetzt weder G0–G5b noch eine fachliche Freigabe. Fehlende
Montserrat-Bold-Messung, fehlende Originale und unvollständige technische oder
menschliche Pflichtprüfungen müssen produktiv offen bleiben.
