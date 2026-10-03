# Handoff — MedizinAnders Codex Pipeline V1

Die lokale V1 ist implementiert, getestet, dokumentiert und auf GitHub abgelegt.
Eine echte Episode wurde noch nicht produziert. Die Betriebsfreigabe G0 und alle
produktiven Human Gates sind weiterhin offen.

- Repository: https://github.com/Lowgiga/medizinanders-codex-pipeline
- Lokaler Checkout: `/workspace/medizinanders-codex-pipeline`
- Getesteter Implementierungsstand: `b5f19ff4152d9bbe0513bad9fcd9828c8d2da10c`
- Format: `MA-SHORT-58-v1.0`, Deutsch, 58 Sekunden, 9:16, 1080 × 1920, 30 fps.
- Das Repository ist auf ausdrücklichen Betreiberwunsch derzeit öffentlich;
  die anschließende Umstellung auf privat übernimmt der Betreiber.

**Durchgeführte Arbeiten**

| Bereich | Gelieferter Umfang |
|---|---|
| Architektur | Lokale Python-CLI `ma`, strukturierte Dateien und Git. Keine Web-App, kein Datenbankserver, kein eigener OpenAI-API-Client. Tatsächlich vorhandene native Codex-Fähigkeiten geprüft. |
| Multi-Agent-System | Getrennte Prompts für ORCHESTRATOR, GAMMA, RESEARCH, ALPHA, BETA und QA/RED TEAM. Registrierte Workerordner mit minimalen Inputs, konkreten Eingabehashes, Schemas und eigener Ergebnisdatei. Native CLI und Übergabe an verfügbare native Subagents; begrenzte Starts und Laufzeit. |
| Recherche und Claims | Verträge für Originalöffnung, tatsächliche Quellensnapshots, Fundstellen, Gegenbelege, Retraktionen, Studienparameter und Unsicherheiten. Vier Claimstatus und separate Einsatzentscheidung. Quellenbehauptung und belegter Sachverhalt werden getrennt geführt. |
| Artefakte und Versionen | JSON-Schemas und YAML-Arbeitsvorlagen für A01–A12; gemeinsame Pflichtmetadaten, Projekt-IDs, SemVer und Abhängigkeitsgraph. Alte Fassungen bleiben erhalten; neue Fassungen erben keine Freigabe. |
| Steuerung und Gates | State-Machine mit G0, G1, G2, G3, G4, G5a und G5b. Interaktive Operatorbestätigung bindet Name, Zeit, konkrete Versionen und Hashes. Status zeigt Blocker, Dateien und nächste Befehle. |
| Fachliche Eskalation | Automatische MEDICAL_REVIEW_PACKET.md und LEGAL_REVIEW_PACKET.md mit Claims, Quellen, geplanten Formulierungen, Unsicherheiten und Fragen. Fehlende notwendige Fachentscheidungen blockieren. |
| Redaktion und Preflight | Prüfungen für Claim-/Satzbindungen einschließlich Metadaten und Overlays, Einsatzbeschränkungen, Wortzahl, eine CTA, lückenlose Timeline, Schnitt bei 3,000 s und stillen Disclaimer 54–58 s. Unabhängige Findings mit Schwere und Rückweg. |
| Freeze und Änderungen | Fortlaufende immutable Revisionen mit A01–A07, Rechteverweisen, Manifest und SHA256SUMS; Freigabe außerhalb des Freeze. Rückwege für Quellen, Bedeutung, Wortlaut, Produktion und Ersatzexporte. |
| InVideo und YouTube | Vollständige kopierbare Produktions-, Szenen-, Sprecher-, Untertitel-, Asset- und Rechtepakete. Uploadmetadaten, Finalhash, echte KI-/Zielgruppen-/Werbeentscheidungen und private Playbackcheckliste. Handoffänderungen werden gegen die geprüften Artefakte geprüft. |
| Video, Audio, Untertitel | Tatsächliche FFmpeg-/ffprobe-Prüfungen, vollständiger Decode, Framezahl, CFR, Codec, Farbraum, MP4/Faststart, GOP, Audioformat, Loudness und True Peak. SRT-Generierung, formale Grenzen und echte Font-Pixelmessung. Unmessbares bleibt offen; kein automatisches Reencoding. |
| Analytics | A12-Ingest realer Daten zur aktuellen dokumentierten Veröffentlichung. Fehlende Werte null mit Begründung, Beobachtung/Hypothese getrennt, genau ein nächster Test, keine automatische Regeländerung. |
| Datenschutz und Betrieb | Produktionsspeicher standardmäßig außerhalb des Repos; strikte rekursive .gitignore, Repository-/Secret-Check, lokale Konfiguration und gesperrte Beispielvorlagen. Getestete Python-Abhängigkeiten festgehalten. Manuell startbarer GitHub-Testworkflow ohne Produktionsaufrufe. |
| Dokumentation und Git | README, AGENTS.md, technischer Vertrag, Kanalprofil, Betreiberkonfiguration, Changelog und Betriebs-/Architektur-/Sicherheitsdokumentation. Abweichungen vom manuellen Ablauf und ungeprüfte historische Angaben ausdrücklich dokumentiert. |

A01–A03 bilden Themenbrief, Quellenakte und Evidenzreview. A04–A06 enthalten
Dramaturgie, Skript/Metadaten und Szenen/InVideo-Auftrag. A07 ist der unabhängige
Preflight. A08–A10 dokumentieren tatsächliche Vorschau, Finaldatei und Medien-QA.
A11 bindet Upload, Playback und die menschlich gemeldete Veröffentlichung;
A12 enthält die spätere Auswertung.

**Nachgewiesene Qualität**

- 183 Tests bestanden, ohne Fehler oder übersprungene Tests; zusätzlich in einer
  frisch installierten Pythonumgebung mit den festgelegten Abhängigkeiten.
- Vollständiger synthetischer DEMO-Durchlauf mit ausdrücklich markierten
  Fixtures und simulierten G0–G3. Ein tatsächlich mit FFmpeg erzeugtes,
  absichtlich fehlerhaftes 58-Sekunden-Video wird korrekt abgewiesen.
  G4/G5 bleiben gesperrt; echte Freigaben und Uploads: null.
- Ein tatsächlicher isolierter nativer GAMMA-Subagent erzeugte ein gültiges A01;
  sein Import wurde geprüft und die Pipeline stoppte anschließend korrekt an G1.
- Eigenes Architekturreview und separater unabhängiger Red-Team-Review.
  Elf Befunde wurden behoben und gegengeprüft; keine offenen Reviewbefunde.
  Darunter Freeze-Manipulationen, veränderte Handoffs, veraltete Upload- und
  Analyticsbindungen sowie unvollständige Playbackchecks.
- Repositoryprüfung ohne erkannte Secrets/Produktionsdateien, Pythoncode
  kompilierbar und Git-Arbeitsverzeichnis sauber. Die beiden Implementierungs-
  commits wurden über die GitHub-Git-Daten-API mit identischen Blob-, Tree- und
  Commit-Hashes übertragen; anschließender `git fetch` bestätigte den Stand.

GitHub verweigerte das Anlegen und die Sichtbarkeitsänderung des Repositories
mit HTTP 403. Der Betreiber legte es selbst an und autorisierte den öffentlichen
Stand. Der normale Git-Push scheiterte mit HTTP 401/403; die tatsächliche
Übertragung über die verfügbare GitHub-API gelang vollständig.

Die vollständige Gatefolge bis A12 wurde in Tests mit deklarierten Testcallbacks
und Messadaptern geprüft. Das belegt die Steuerung, keinen echten InVideo-Render,
Fachreview, Smartphonecheck oder Plattformvorgang. Eine reale Webrecherche zur
ersten Episode und eine vollständige produktive Videoproduktion stehen noch aus.

**Übernahme und erste Episode**

Voraussetzungen: Linux/macOS beziehungsweise WSL, Python 3.11+, Git, tatsächlich
funktionierende Codex-Laufzeit sowie FFmpeg/ffprobe.

```bash
git clone https://github.com/Lowgiga/medizinanders-codex-pipeline.git
cd medizinanders-codex-pipeline
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-lock.txt -e .
ma setup
ma doctor
```

Die von `ma setup` genannte lokale operator.yaml ausfüllen. Nur tatsächlich
geprüfte Angaben bestätigen. Codex anmelden und die reale Laufzeit/Webrecherche
prüfen; anschließend entscheidet der Betreiber selbst G0:

```bash
codex login
ma approve G0 --name 'DEIN NAME'
ma new
```

`ma new` fragt nach der Themenidee und nennt die Projekt-ID. Danach
`ma run <PROJEKT-ID>`; nach erledigten Gates oder manuellen Übergaben
`ma resume <PROJEKT-ID>`. `ma status <PROJEKT-ID>` zeigt die nächste Aufgabe.
Produktionsdateien liegen standardmäßig in
`~/.local/share/medizinanders/projects/`, nicht im Git-Checkout.

**Verbleibende menschliche Aufgaben**

| Gate | Tatsächlich auszuführende Handlung |
|---|---|
| G0 | Betrieb, Verantwortung, Datenschutz, Speicher und echte Werkzeuge bestätigen. |
| G1 | Themenauftrag, Scope, Rechercheaufwand und offene Entscheidungen freigeben. |
| G2 | Claims, Originalquellen, Gegenbelege, Einschränkungen und Risiken prüfen; notwendige echte medizinische/juristische Reviews einholen. |
| G3 | Freeze und Auftrag freigeben; InVideo selbst bedienen und Kosten selbst akzeptieren. Preview unter dem angezeigten Inboxpfad ablegen. |
| G4 | Tatsächliche Vorschau vollständig ansehen und hören, einschließlich Smartphone, Wortlaut, Aussprache, Untertiteln, Disclaimer und Rechten. |
| G5a | Konkrete Finaldatei/SRT und Uploadentscheidungen bestätigen; manuell ausschließlich privat hochladen und Video-ID/URL zurückmelden. |
| G5b | Verarbeitetes privates Plattformvideo vollständig kontrollieren; danach selbst veröffentlichen und die Veröffentlichung dokumentieren. |

**Offene G0-Angaben und bekannte Grenzen**

- Verantwortliche Person, tatsächliche Umgebung und privater Speicherort;
  Datenschutzentscheidung, Rollenprüfung und reale Toolmöglichkeiten.
- Funktionierender Codex-/Webzugang und tatsächliche InVideo-Exportmöglichkeiten.
  Die hier installierte Codex CLI 0.159.0-alpha.3 scheiterte bei einem echten
  Lauf mit HTTP 401. Der native Subagent-Übergabeweg funktionierte. Bei einem
  CLI-Problem bereitet `ma run <ID> --prepare-only` den isolierten Auftrag vor.
- Tatsächliches Budget pro Episode und Zeitlimit, Zielgruppe und Sprecherwahl.
  Die historischen Beträge 4 / 4,5 / 12 Euro wurden nicht als Freigabe übernommen.
  Eine männliche Stimme ist lediglich der dokumentierte Standardvorschlag.
- Echte Montserrat-Bold-Datei unter font_path bereitstellen. SRT-Zeitstempel
  müssen zum tatsächlichen Audio geprüft werden; ein Prompt garantiert keine
  InVideo-Exporteinstellungen. Nicht zuverlässig messbare Musiktrennung führt
  zum verbindlichen Fallback: Musik entfernen.
- Kontexttrennung ist keine harte OS-Leseisolation. Hashes beweisen Bytebindung,
  keine wissenschaftliche Wahrheit, Identität, Fachqualifikation oder Rechte.
  Keine automatische C2PA-Verifikation und keine fingierte Fachfreigabe.
- Repository anschließend privat stellen und den im Chat geteilten GitHub-Token
  widerrufen. Der Token wurde nicht in das Repository aufgenommen.

Maßgebliche Unterlagen: [README](../README.md),
[technischer Vertrag](../IMPLEMENTATION_CONTRACT.md),
[Pipeline und Artefakte](pipeline.md), [Human Gates](human-gates.md),
[manuelle Schritte](manual-steps.md), [Video-QA](video-qa.md),
[Datenschutz](security.md), [Testnachweise](verification.md),
[Architekturreview](architecture-review.md) und
[unabhängiger Review](red-team-review.md).
