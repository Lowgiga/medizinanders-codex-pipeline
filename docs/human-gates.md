# Menschliche Gates und Reviews

Ein Gate dokumentiert eine konkrete Entscheidung des lokalen Operators auf
aktuellen Artefaktversionen und Hashes. Die produktive CLI verlangt eine
interaktive Bestätigung; es gibt kein `--yes`. Ein Agent kann Findings und
Review-Pakete erstellen, aber niemals ein Gate oder eine fachliche Freigabe geben.
Die CLI vertraut dem lokalen Operator. Der eingetragene Name beweist weder
Identität noch Qualifikation.

| Gate | Entscheidung | Erforderliche Grundlage |
|---|---|---|
| G0 | Arbeitsumgebung und Verantwortung | Verantwortliche Person, Umgebung, Datenschutz, geprüfte Rollenprompts, Speicher, tatsächliche Tools/InVideo-Möglichkeiten, Codex-/Recherche-Nutzung, Budget, Zeit, Zielgruppe und ausdrückliche Stimmwahl |
| G1 | Thema und Scope | Aktuelles A01; klare Kernfrage, Nutzen, Ausschlüsse, Suchfragen und verfügbare Ressourcen |
| G2 | Verwendbare Claims | Aktuelles A03 und seine Eingaben; echte Quellenfundstellen, Claimstatus, Einsatzentscheidung, Gegenbelege, Einschränkungen und Risiken; bei Prüfbedarf echte medizinische bzw. juristische Entscheidung |
| G3 | Redaktioneller Freeze und Handoff | Aktuelle A01–A06, A07 `freigabefaehig`, vollständige Pflichtprüfungen, geschlossene blockierende Findings, geklärte Assets/Rechte und Freeze |
| G4 | Preview | Tatsächlich gerenderte Previewbytes, ihr SHA-256, technischer Report und vollständige menschliche Sicht-/Hörprüfung des gleichen Videos |
| G5a | Final und privater Upload | Tatsächliche Finalbytes, ihr SHA-256, A09/A10, SRT, technische und menschliche Finalprüfung sowie Zielgruppe, Werbung und KI-Kennzeichnung |
| G5b | Freigabe zur manuellen Veröffentlichung | Echter privater Upload, Video-ID/URL, abgeschlossene Plattformverarbeitung und menschliche Playback-Prüfung des verarbeiteten privaten Videos |

Ein vollständig ausgefülltes Formular erfüllt nicht automatisch die zugehörige
Prüfung. Offene Blocker, `nicht_geprueft`-Ergebnisse, fehlende Originale, aktuelle
Hashkonflikte oder eine benötigte, fehlende Fachentscheidung sperren das Gate.
Demo-Gates sind immer `DEMO_SIMULATION`; sie zählen nie für Produktion.

## Operatorbefehle

```sh
ma approve G0 --name 'Operatorname'
ma approve G1 --project MA-YYYYMMDD-NNN --name 'Operatorname'
ma approve G2 --project MA-YYYYMMDD-NNN --name 'Operatorname'
ma approve G3 --project MA-YYYYMMDD-NNN --name 'Operatorname'
ma approve G4 --project MA-YYYYMMDD-NNN --name 'Operatorname'
ma approve G5a --project MA-YYYYMMDD-NNN --name 'Operatorname'
ma approve G5b --project MA-YYYYMMDD-NNN --name 'Operatorname'
```

Diese Befehle lösen die konkrete interaktive Bestätigung aus. Der Name ist eine
lokale Erklärung und kein Authentifizierungsmechanismus. Projektbezogene
Freigaben beziehen sich auf den angezeigten Stand; nach einer relevanten Änderung
müssen die betroffenen Gates erneut auf neuen Nachweisen entschieden werden.

## Medizinische und rechtliche Entscheidungen

A03 benennt medizinisch und rechtlich relevante Claims sowie den tatsächlichen
Reviewbedarf. Die Pakete unter `project/review/` enthalten betroffene Claim-IDs,
Wortlaut, Originalfundstellen, Evidenzgrenzen, konkrete Risiken, öffentliche
Formulierungen und offene Fragen. Sie dürfen eine Entscheidung nicht vorwegnehmen.
Der Operator organisiert eine geeignete menschliche Prüfung. Ein redaktioneller
Agententwurf, die Person, die den Import klickt, oder eine allgemeine Disclaimer-
Zeile ersetzt diese fachliche Entscheidung nicht.

```sh
ma review medical --project MA-YYYYMMDD-NNN --file Entscheidung.json
ma review legal --project MA-YYYYMMDD-NNN --file Entscheidung.json
```

Die Entscheidung muss sich auf den aktuellen Claimstand und die tatsächlich
geprüften Unterlagen beziehen. Ihr Import verlangt interaktive Bestätigung.
Geänderte Aussagen, Evidenz oder Risiken erfordern neue Reviews. Die V1 prüft
keine staatliche Registrierung des Prüfers und enthält keine pauschale
regulatorische Denylist. Der Operator bleibt für die Wahl eines geeigneten
Prüfers und die Echtheit der Entscheidung verantwortlich.

Die erzeugten `review/medical.decision.example.json` und
`review/legal.decision.example.json` sind ungeprüfte Vorlagen. Eine echte
Entscheidung nennt `reviewer`, `qualification`, `notes`, `claim_ids`,
`reviewed_packet_sha256` und `decision` (`approved`, `rejected` oder
`changes_required`). Sie muss sämtliche verwendbaren Claim-IDs abdecken und den
Hash des tatsächlich geprüften aktuellen Pakets treffen. Eine Fachentscheidung
erteilt selbst kein Pipelinegate. Ein später ergänzter öffentlicher Wortlaut
kann das Review-Paket ändern und verlangt dann eine erneute Fachentscheidung.

## Atteste für konkrete Medien

```sh
ma attest MA-YYYYMMDD-NNN --stage preview --file preview-check.json
ma attest MA-YYYYMMDD-NNN --stage final --file final-check.json
ma attest MA-YYYYMMDD-NNN --stage playback --file playback-check.json
```

Jedes Attest benennt die konkrete geprüfte Stufe und bindet die Bestätigung an
aktuelle Medienhashes; Playback bezieht sich zusätzlich auf den echten privaten
Upload. Es muss die tatsächliche Prüfung abbilden. Andere Bytes, ein erneuter
Export oder ein anderer Upload sind neue Prüfgegenstände.

Vorlagen heißen `handoff/invideo/PREVIEW_CHECKLIST.example.json`,
`FINAL_CHECKLIST.example.json` und
`handoff/playback/PLAYBACK_CHECKLIST.example.json`. Die echten ausgefüllten
Dateien nennen `operator`, `checked_at`, den aktuellen Preview-/Finalhash,
`checks` und konkrete `evidence`; `example` wird ausdrücklich `false` gesetzt.
Die zwölf verpflichtenden Check-IDs sind `voiceover_exact`, `pronunciation`,
`subtitle_sync_100ms`, `subtitle_visual`, `font_layout`, `burned_subtitles`,
`smartphone_listening`, `disclaimer_visual`, `rights`, `ai_label`,
`patient_privacy` und `audio_music_verified`. Playback ergänzt die tatsächliche
Plattformverarbeitung, vollständige Wiedergabe und Metadatenentscheidungen.
Offene technische Checks dürfen nur mit einem tatsächlich passenden konkreten
Nachweis in `technical_unknowns` behandelt werden, nicht durch pauschales Abhaken.
Die dafür vorgesehenen IDs sind `video_bitrate_target`, `video_vbv_maxrate`,
`audio_bitrate`, `ending_visual_disclaimer` und `audio_video_sync`. Jeder Eintrag
benennt `nachweis` als vorhandene Projektdatei und deren tatsächlichen `sha256`.
Andere unvollständige technische Pflichtchecks bleiben blockiert. Messfehler
werden nicht durch ein Attest überstimmt; die konkreten Medien werden korrigiert
und erneut geprüft.

Für Preview und Final prüft der Mensch das ganze Video: richtigen Inhalt,
Claim- und Einschränkungstreue, verständliche Stimme, Timing, harten Schnitt bei
3 Sekunden, lesbare korrekte Untertitel und Quellenhinweise, Safe Area, passende
Assets und Rechte, keine irreführende KI-Illustration oder imitierte Stimme,
genau einen CTA und den schwarzen stillen Disclaimer von 54 bis 58 Sekunden.
Technische Messwerte und sicht-/hörbare Sachverhalte werden zusammengeführt,
aber nicht gegenseitig ersetzt.

Playback wird nach abgeschlossener Plattformverarbeitung am privaten Upload
geprüft: richtige Video-ID und vollständige Laufzeit, Bild und Ton von Anfang bis
Ende, Untertitel, Synchronität, Quellenhinweise, Disclaimer und passende Upload-
Metadaten. Ein lokaler Finalcheck beweist dieses Plattformresultat nicht.

## Änderung und erneute Prüfung

`ma invalidate <ID> --change source|meaning|wording|production|export --reason '…'`
erfasst einen Rückweg. Bei Quellen- oder Bedeutungsänderungen muss die Evidenz- und
Claimprüfung erneut erfolgen. Bei Wortlautänderungen müssen faktische Bindungen
und redaktioneller Freeze erneut passen. Produktionsänderungen benötigen neue
Medienprüfungen. Ein neuer Export benötigt neue Hashbindungen und erneute
Prüfungen der konkreten Medien. Keine bestehende Freigabe darf auf neue Bytes
oder neue Aussagen übertragen werden.

## Freigabestatus im unveränderlichen Freeze

G1 und G2 erzeugen die erste bestätigte Fassung als `1.0.0` mit Status
`freigegeben`. Bereits vor der Bestätigung zeigt die CLI genau deren Versionen
und vorberechnete Dateihashes an. Die unveränderten Entwürfe bleiben erhalten.

Für G3 werden die geprüften A04–A07-Kandidaten bereits vor dem Freeze als
`1.0.0` gespeichert. Ihr gespeichertes Statusfeld bleibt `geprüft`; die wirksame
menschliche Produktionsfreigabe steht im separaten, hashgebundenen G3-Record.
Dadurch ändert das Bestätigen keinen eingefrorenen Dateibyte. Ein Statusfeld
allein gilt in keiner Stufe als Ersatz für ein gültiges Human Gate.

Ein unveränderter Vorschaucheck G4 bleibt nach einem neuen Finalexport gültig.
G5a/G5b und die Final-/Playbacknachweise müssen zum neuen Export erneut entstehen.
Änderungen an abgeleiteten Handofftexten blockieren das Gate auch dann, wenn alle
Dateien vorhanden sind. `ma repair-handoff <ID>` stellt ausschließlich den
ursprünglich geprüften Inhalt wieder her und erteilt keine Freigabe.
