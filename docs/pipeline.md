# Pipeline und Artefakte

Die Pipeline verwendet zwölf versionierte Artefakte. Der erste Entwurf ist
`0.1.0` mit Status `Entwurf`; weitere Bearbeitungen erzeugen neue Versionen.
Produktionsartefakte tragen Projekt-ID, Autor, Datum, Quellen-IDs, offene Punkte,
Sperrstatus und SHA-256-Bindungen an ihre tatsächlichen Vorgänger.

| Artefakt | Inhalt / Verantwortung | Gebundene Vorgänger |
|---|---|---|
| A01 | Themenbrief / GAMMA | keine |
| A02 | Quellenakte / RESEARCH | A01 |
| A03 | Claims, Faktenmatrix, Risiken / ALPHA | A01, A02 |
| A04 | Dramaturgie / BETA | A03 |
| A05 | Skript und sämtliche öffentlichen Textflächen / BETA | A03, A04 |
| A06 | Szenen, Assets, Rechte und InVideo-Prompt / BETA | A03, A04, A05 |
| A07 | Preflight / QA-RED-TEAM | A01–A06 |
| A08 | Tatsächlicher Preview-Rendernachweis / Orchestrator und Operator | A07 |
| A09 | Finalvideo, SRT, Änderungen und Audiobehandlung / Orchestrator und Operator | A05, A06, A08 |
| A10 | Technische und menschliche Medien-QA / Orchestrator | A07, A08, A09 |
| A11 | Upload-, Playback- und Veröffentlichungsnachweis / Operator | A05, A10 |
| A12 | Analytics, Beobachtungen, ein nächster Test / Operator und Orchestrator | A11 |

Ein neuer Hash oder eine neue Vorgängerversion erfordert neue abhängige Bindungen.
Ein gültiges JSON-Schema reicht nicht: Quellenzugang, Claimkonsistenz, Rechte,
Reviewbedarf, offene Findings und aktuelle Gatebindungen werden separat geprüft.
Der unabhängige A07-Preflight verwendet die Pflichtprüfungs-IDs
`claim_sentence_map`, `sources_originals`, `counterevidence_uncertainty`,
`medical_legal_escalation`, `timeline_cta_disclaimer`, `assets_rights` und
`invideo_complete` mit jeweils tatsächlichem Nachweis.

## Ablauf und Stopps

1. `ma doctor` prüft lokale Voraussetzungen und tatsächlich verfügbare
   Codex-CLI-Fähigkeiten. `ma setup` legt die lokale Operator-Konfiguration an.
   G0 bestätigt Verantwortung, Datenschutz, Rollenprompts, Speicher, Toolmöglichkeiten,
   Budget, Zeit, Zielgruppe und Stimme. Männliche Stimme ist ein Standardvorschlag.
2. `ma new --topic '…'` legt das Projekt an; ohne Thema ist die Themenabfrage
   interaktiv. `ma run <ID>` startet GAMMA und hält bei G1 für A01.
3. Nach G1 laufen RESEARCH und ALPHA. G2 prüft A03, alle verwendbaren Claims,
   Quellenbelege und bei Bedarf echte medizinische oder juristische Entscheidungen.
4. Nach G2 erzeugt BETA A04–A06. QA-RED-TEAM erzeugt A07. G3 verlangt aktuelle
   A01–A06, `freigabefaehig` in A07 und einen Freeze. Freeze und Handoff werden
   zur Prüfung vor G3 vorbereitet; genutzt werden sie erst nach G3.
   Danach stoppt die Pipeline für die manuelle Produktion.
5. Der Operator rendert und prüft den Preview. `ma qa <ID> --file <preview.mp4>
   --kind preview` erstellt technische Reports; `ma attest <ID> --stage preview
   --file <JSON>` dokumentiert die konkrete menschliche Prüfung des tatsächlichen
   Hashes. G4 braucht beide Prüfarten und den echten Rendernachweis.
6. Der Operator erzeugt Finalvideo und SRT. `ma qa <ID> --file <final.mp4>
   --kind final` und `ma attest <ID> --stage final --file <JSON>` binden technische
   und menschliche Ergebnisse an die Finalbytes. G5a verlangt A09, A10, SRT,
   menschliche Prüfungen und die Uploadentscheidungen.
7. Der Operator lädt manuell privat hoch, wartet auf Plattformverarbeitung und
   registriert mit `ma youtube private <ID> --id <YOUTUBE_ID> --url <URL>` den
   echten privaten Upload. Die vollständige Playback-Prüfung wird über
   `ma attest <ID> --stage playback --file <JSON>` gebunden. Erst dann ist G5b
   möglich. Die öffentliche Veröffentlichung erfolgt manuell; ihr Nachweis wird
   mit `ma youtube published <ID> --url <URL>` erfasst.
8. `ma analytics <ID> --file <analytics.json>` erstellt A12. Beobachtungen und
   Hypothesen bleiben getrennt, fehlende Messwerte erhalten eine Begründung.
   Genau ein nächster Test wird vorgeschlagen; `regel_aenderung` bleibt `false`.

`ma resume <ID>` setzt an der nächsten zulässigen Stufe fort. `ma status <ID>`
zeigt aktuellen Stand und Blocker. `ma import <ID> --file <result.json>` nimmt
einen Workerentwurf unter denselben Struktur- und Abhängigkeitsprüfungen an.
`ma invalidate <ID> --change source|meaning|wording|production|export --reason '…'`
meldet eine Änderung und erzwingt den entsprechenden Rückweg. Freigaben werden
nicht durch das Fortsetzen, einen Import oder das Vorhandensein einer Datei ersetzt.

## Redaktionelles Profil MA-SHORT-58-v1.0

Das Video dauert genau 58,000 Sekunden, umfasst bei konstanten 30/1 fps
1.740 Frames und enthält 100–130 gesprochene deutsche Wörter. Bei 3.000 ms liegt
ein harter Schnitt; genau ein CTA ist erlaubt. Sprechertext und Quellenbelege
müssen in diesen Umfang passen. Kürzungen dürfen keine Einschränkung entfernen.

| Abschnitt | Zeit |
|---|---|
| Hook | 0–3 Sekunden |
| Open Loop | 3–8 Sekunden |
| Payload | 8–41 Sekunden |
| Verdichtung | 41–48 Sekunden |
| CTA | 48–52 Sekunden |
| Ausklang | 52–54 Sekunden |
| Disclaimer | 54–58 Sekunden |

Der letzte Abschnitt zeigt ausschließlich einen schwarzen Hintergrund und den
festen Text `Journalistischer Analyse-Content. Kein medizinischer Rat.`.
Er ist still: kein Voiceover, keine Musik und keine zusätzlichen Bildinhalte.

## Technisches Profil

| Bereich | Vorgabe |
|---|---|
| Bild | 1080 × 1920, SAR 1:1, progressiv, CFR 30/1 fps, yuv420p, SDR BT.709 |
| Codec | H.264/AVC High, Level 4.1; 10 Mbit/s Ziel, höchstens 16 Mbit/s; Closed GOP höchstens 60 Frames, B-Frames 2 |
| Container | MP4 mit Faststart |
| Audio | AAC-LC, 48 kHz, Stereo, 384 kbit/s Ziel |
| Lautheit | −14 LUFS Ziel, zulässig −15 bis −13 LUFS; True Peak höchstens −1,5 dBTP |
| Musik | Instrumental, kein Gesang, keine dramatischen Stings; Ziel 18 dB unter Stimme, zulässig 15–21 dB |
| Fehlende getrennte Audiotracks | Musik entfernen, wenn der Abstand nicht zuverlässig aus getrennten Spuren messbar ist |
| Untertiteldatei | Deutsch, UTF-8 SRT, zusätzlich korrekt eingebrannt |
| Schrift | Montserrat Bold, 52 px, weiß |
| Lesbarkeit | Höchstens 2 Zeilen und 28 Zeichen pro Zeile, höchstens 18 Zeichen/s |
| Cuezeiten | 0,80–4,00 Sekunden, Synchronfehler höchstens 100 ms |
| Safe Area | x = 90–930, y = 192–1536; Untertitelunterkante höchstens y = 1520 |
| Quellenhinweise | y = 1200–1320, lesbar und ohne Untertitelüberschneidung |

Die Profilvorgabe ist kein Bericht, dass ein konkretes Tool sie einhalten kann.
G0 erfasst tatsächliche InVideo-Möglichkeiten. Unmessbare Anforderungen werden
als `nicht_geprueft` geführt und bleiben für die entsprechende Freigabe offen.
SRT allein beweist weder Einbrennen, Schrift, Position noch Synchronität im Video.

## Handoff nach G3

Unter `project/handoff/invideo/` liegen diese acht Handoff-Inhaltsdateien:

1. `INVIDEO_PROMPT.txt` – Produktionsanweisung aus A06.
2. `SCENE_PLAN.md` – Zeiten, Funktionen, Motive und Synchronanker.
3. `VOICEOVER.txt` – freigegebener Sprechertext.
4. `SUBTITLE_BASE.txt` – freigegebene Untertitelbasis.
5. `ASSET_MANIFEST.yaml` – Assets, Herkunft, Rechte und KI-/Stimmenangaben.
6. `RIGHTS_CHECKLIST.md` – konkrete Rechte- und Nachweispunkte.
7. `EXPECTED_OUTPUT.md` – verbindliche Zielausgabe und Prüfanforderungen.
8. `OPERATOR_STEPS.md` – manuelle Produktion, Export und Rücklieferung.

Daneben werden `PREVIEW_CHECKLIST.example.json` und
`FINAL_CHECKLIST.example.json` als ungeprüfte Vorlagen vorbereitet. Der Operator
füllt daraus eigene Checklisten aus. Vorlagen und ein vorbereiteter Handoff
erteilen keine Freigabe und dürfen vor G3 keinen Render auslösen.

Claimbezogene fachliche Pakete liegen getrennt unter
`project/review/MEDICAL_REVIEW_PACKET.md` und
`project/review/LEGAL_REVIEW_PACKET.md`. Rückgelieferte Medien liegen unter
`project/08_produktion/inbox/preview.mp4`, `final.mp4` und `subtitles.srt`.
Das Erstellen des Handoffs beweist keinen Render, keine Rechteklärung und keine
Toolunterstützung. Jede Änderung am eingefrorenen Inhalt erfordert den passenden
Rückweg und neue Freigabebindungen.

Der manuelle Upload wird unter `project/handoff/youtube/` mit
`YOUTUBE_HANDOFF.md`, Metadaten, SRT und
`YOUTUBE_DECISIONS.example.json` vorbereitet. Eine echte Operatorentscheidung
liegt als `YOUTUBE_DECISIONS.json` daneben. Nach Registrierung des privaten
Uploads liegen `PLAYBACK_STEPS.md` und `PLAYBACK_CHECKLIST.example.json` unter
`project/handoff/playback/`; die ausgefüllte Datei heißt
`PLAYBACK_CHECKLIST.json`.
