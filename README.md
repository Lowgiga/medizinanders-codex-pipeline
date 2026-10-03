# MedizinAnders Codex Pipeline

Lokale Produktionsumgebung für journalistisch-analytische deutsche Gesundheitsvideos.
Codex recherchiert und schreibt in getrennten Kontexten. Die CLI prüft Dateien,
verwaltet Versionen und stoppt mit konkreten Anweisungen an jedem Human Gate.
InVideo und YouTube werden manuell bedient. Es gibt keinen Server und keine eigene
OpenAI-API-Abhängigkeit.

## Einmal einrichten

Voraussetzungen: Linux oder macOS, Python 3.11+, Git, angemeldete Codex CLI und
FFmpeg einschließlich ffprobe. Windows: WSL verwenden. Installiere aus diesem
Checkout; eine alleinstehende Wheel-Installation wird in V1 nicht unterstützt.

```bash
cd medizinanders-codex-pipeline
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-lock.txt -e .
ma setup
ma doctor
```

`ma setup` nennt den **einen lokalen Konfigurationspfad**. Öffne dort
`operator.yaml`, trage Name, Umgebung, Zielgruppe, Stimme, Budget und Zeit ein und
prüfe Datenschutz, Speicher, Rollenprompts und echte Toolmöglichkeiten. Mit
`true` nur tatsächlich geprüfte Punkte bestätigen. Hinterlege unter `font_path`
eine echte Montserrat-Bold-Schriftdatei für die Pixelmessung. Die Produktion
akzeptiert dafür keine Ersatzschrift und keine bloße Bestätigung.

Prüfe vor G0, dass Codex in deiner eigenen Umgebung wirklich arbeiten kann:

```bash
codex login
ma approve G0 --name 'DEIN NAME'
```

Die CLI zeigt vor jeder Freigabe die genaue Bedeutung, Versionen und Hashes.
Tippe die angezeigte Bestätigungszeile im Terminal selbst ein. Agenten dürfen
diesen Befehl niemals für dich ausführen. Es gibt keine `--yes`-Option.

## Erste echte Episode

```bash
ma new --topic 'DEINE THEMENIDEE'
```

Der Befehl nennt deine Projekt-ID und den nächsten Befehl, zum Beispiel:

```bash
ma run MA-20261003-001
```

GAMMA erstellt A01. Die Pipeline wartet dann auf G1. Danach arbeitet `ma resume`
bis zum nächsten Gate weiter. Du brauchst keine Dateinamen zu erraten:

```text
STATUS: WAITING_FOR_HUMAN
GATE: G2
WHY: Pflicht-medical-Fachprüfung fehlt.

Next:
1. Lass .../review/MEDICAL_REVIEW_PACKET.md von einer echten Fachperson prüfen.
2. Dokumentiere die echte Entscheidung mit dem angezeigten ma review-Befehl.
3. ma approve G2 --project MA-... --name 'DEIN NAME'
```

Produktionsdateien liegen standardmäßig in `~/.local/share/medizinanders/projects/`.
Der Speicher ist außerhalb des Git-Repositories; `MA_HOME` kann auf einen anderen
privaten lokalen Ordner zeigen. Gemeinsame Netzwerkordner werden in V1 nicht
unterstützt. Git enthält ausschließlich Pipeline-Code und synthetische Beispiele.

## Die wenigen manuellen Stellen

| Stelle | Deine Aufgabe |
|---|---|
| G0 | Betrieb und tatsächliche Werkzeuge bestätigen |
| G1 | Themenauftrag, Scope und Aufwand freigeben |
| G2 | Claims, Quellen, Einschränkungen und Risiken freigeben; bei Bedarf echten medizinischen/juristischen Review einholen |
| G3 | Freeze und Produktionsauftrag prüfen; anschließend einen Entwurf in InVideo erzeugen und Kosten selbst entscheiden |
| G4 | Tatsächliche Vorschau sehen/hören, Smartphone, Wortlaut, Untertitel und Rechte prüfen |
| G5a | Konkrete Finaldatei und Uploadentscheidungen freigeben; ausschließlich privat hochladen |
| G5b | Verarbeitetes privates YouTube-Video vollständig prüfen; danach selbst öffentlich stellen |

Nach InVideo die echte Vorschau unter dem angezeigten Pfad
`08_produktion/inbox/preview.mp4` ablegen und ausführen:

```bash
ma resume MA-...
```

FFmpeg misst die tatsächliche Datei und schreibt Rohdaten und Reports nach
`10_qa/`. Fehler bleiben Fehler; die CLI encodiert nichts automatisch um.
Die ungeprüften Checklisten enthalten zunächst ausschließlich `false`.
Trage nur persönlich erledigte Prüfungen ein und registriere sie mit dem
angezeigten `ma attest`-Befehl. Finalexport und `subtitles.srt` kommen erst nach G4
in denselben Inbox-Ordner. Bei nicht verlässlich messbarer Musik-/Stimmtrennung
ist der verbindliche Fallback: **Musik entfernen**.

Encoder-Zielwerte und visuelle/synchrone Eigenschaften benötigen echte ergänzende
Nachweise. Unter `technical_unknowns` trägst du für die im Report genannten
zulässigen Prüfungen je `{ "nachweis": "review/DEIN_NACHWEIS.md", "sha256": "..." }`
ein. Nur vorhandene, selbst erstellte Prüfnotizen oder echte Exporteinstellungen
verwenden. Den Hash erhältst du mit `sha256sum DATEI` (macOS: `shasum -a 256 DATEI`).
Fehlgeschlagene Messungen können mit einer Checkliste nicht überstimmt werden.

Vor G5a `YOUTUBE_DECISIONS.example.json` als `YOUTUBE_DECISIONS.json` ausfüllen:
`example: false`, tatsächliche KI-Kennzeichnung, Zielgruppe und Werbung entscheiden,
Final- und SRT-Hash beibehalten. Nach privatem Upload:

```bash
ma youtube private MA-... --id VIDEO_ID --url 'https://www.youtube.com/watch?v=VIDEO_ID'
```

Die Pipeline erzeugt die Playback-Checkliste. Nach echter Plattformkontrolle,
Playbackattest und G5b stellst du das Video selbst öffentlich und dokumentierst es:

```bash
ma youtube published MA-... --url 'https://www.youtube.com/watch?v=VIDEO_ID'
```

## Änderungen und Fehler

`ma status MA-...` zeigt den nächsten Schritt. Eine neue Version erbt keine
Freigabe. Verwende für eine Änderung den passenden Rückweg:

```bash
ma invalidate MA-... --change source --reason 'Neue Studie oder korrigierte Zahl'
ma invalidate MA-... --change meaning --reason 'Medizinische Einordnung geändert'
ma invalidate MA-... --change wording --reason 'Titel oder Sprechertext geändert'
ma invalidate MA-... --change production --reason 'Szene, Bild oder Musik geändert'
ma invalidate MA-... --change export --reason 'Neuer Finalexport'
```

Dateien direkt zu bearbeiten erzeugt einen Hashfehler. Ändere bestehende
Artefaktversionen und Freeze-Verzeichnisse nicht. Abgeleitete beschädigte/fehlende
Handoff-Dateien lassen sich aus unveränderten Originalen wiederherstellen:
`ma repair-handoff MA-...`. Eine Änderung an Regeln oder G0-Konfiguration verlangt
eine erneute Betriebsfreigabe; bei geänderten Regeln den redaktionellen Rückweg nutzen.

## Wenn die native Codex-Laufzeit fehlt

Der Build hat echte native Subagents verwendet. Die hier installierte Codex CLI
`0.159.0-alpha.3` wurde zusätzlich getestet: Ihr Laufzeitaufruf scheiterte am
03.10.2026 mit HTTP 401. Ein angezeigter Login allein beweist keinen funktionierenden
Zugriff. In deiner eigenen Umgebung erneut anmelden; Tokens niemals hier eintragen.

Die Pipeline bereitet bei einem Fehler den isolierten Worker-Auftrag vollständig
vor und nennt `START_HERE.md`. In einer Codex-Sitzung mit nativen Subagents kann
der Orchestrator dessen Rolle mit **frischem Kontext** übernehmen. Der gleiche
Weg lässt sich ausdrücklich vorbereiten:

```bash
ma run MA-... --prepare-only
```

Codex liest die genannte `START_HERE.md`, startet einen verfügbaren nativen
Subagent mit ausschließlich den erlaubten Dateien und liefert `result.json`.
Danach den dort angegebenen `ma import`-Befehl verwenden. Die CLI simuliert keine
Subagent-Funktion und wechselt nicht auf einen eigenen API-Client.

## Später Analytics auswerten

Exportiere die realen YouTube-Daten zur veröffentlichten Episode und lege sie
außerhalb des Repos ab. Lass Codex daraus nach
[dem Eingabeformat](docs/manual-steps.md#analytics) eine lokale `analytics.json`
erstellen. Fehlende Werte bleiben `null` mit Grund, Beobachtungen und Hypothesen
stehen getrennt, genau ein nächster Test. Danach:

```bash
ma analytics MA-... --file /DEIN/PRIVATER/PFAD/analytics.json
```

Der Import erstellt A12 und ändert keine Kanalregel.

## Testen und nachlesen

```bash
python3 -m unittest discover -s tests -v
ma demo --with-video
python3 scripts/check_repository.py
```

Der DEMO-Speicher ist getrennt, alle Freigaben tragen `DEMO_SIMULATION`.
Das falsche synthetische Testvideo muss durchfallen; G4/G5 bleiben blockiert.
Niemand hat dadurch InVideo bedient, ein echtes Video geprüft oder veröffentlicht.
Den bereinigten Ergebnisbericht nennt `ma demo`. Die Tests prüfen zusätzlich den
kompletten späteren Operatorablauf mit ausdrücklich simulierten Testcallbacks.

[Pipeline](docs/pipeline.md), [Human Gates](docs/human-gates.md),
[manuelle Schritte](docs/manual-steps.md), [Video-QA](docs/video-qa.md),
[Datenschutz](docs/security.md), [Architektur](docs/architecture.md),
[Abweichungen](docs/deviations-from-manual-spec.md),
[Testnachweise](docs/verification.md), [Red-Team-Review](docs/red-team-review.md).
