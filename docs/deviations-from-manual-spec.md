# Abweichungen und Präzisierungen

Die V1 macht den berichteten manuellen Ablauf ausführbar, ohne unprüfbare Angaben
aus dem historischen Export zu übernehmen. Maßgeblich ist
`IMPLEMENTATION_CONTRACT.md`. Wo `EXPORT-AVS-001` widersprüchlich oder ohne
Originalnachweis ist, dokumentiert `historical-export.md` den offenen Status.

| Thema | V1-Entscheidung und Grund |
|---|---|
| Laufzeit | Ein Profil: `MA-SHORT-58-v1.0`, 58,000 Sekunden / 1.740 Frames. Die berichtete Alternative 1–3 Minuten ist nicht implementiert. |
| Agentenlaufzeit | Frische native `codex exec`-Worker mit minimalen Eingaben; kein eigener OpenAI-API-Client und kein gemeinsamer Chat als State. |
| Freigaben | Nur konkrete interaktive Operatorentscheidungen; medizinische und rechtliche Reviews sind echte externe menschliche Entscheidungen. Keine Agentfreigaben. |
| Automation | Recherche- und Entwurfsarbeit sowie prüfbare lokale Dateischritte werden koordiniert. Rendering, Toolbedienung, Upload, Plattformverarbeitung und Veröffentlichung benötigen die dokumentierten manuellen Schritte. |
| Veröffentlichung | Keine automatische Veröffentlichung, kein YouTube-API-Upload. G5b prüft das verarbeitete private Video vor der manuellen Veröffentlichung. |
| Oberfläche und Kanäle | Lokale CLI und Projektverzeichnisse. Keine Weboberfläche, Datenbank oder Mehrkanalsteuerung in V1. |
| Quellen | Suchtreffer und Snippets bleiben Suchhinweise. Nur tatsächlich geöffnete Originale mit konkreten Fundstellen und Byte-Snapshots können als geprüft gelten. |
| Rechte und Provenienz | Nachweise müssen vorliegen. Flags sind keine Prüfung; keine behauptete automatische oder geprüfte C2PA-Verifikation. |
| Regeln zu medizinischen und rechtlichen Risiken | Claimbezogene Review-Pakete und Prüferentscheidungen; keine aus pauschalen regulatorischen Denylists erzeugte Freigabe oder Sperre. |
| Stimme | Männlich ist ein Standardvorschlag aus dem berichteten Export, keine automatisch bestätigte Wahl. G0 hält die Entscheidung fest. |
| Kosten | Historische Zahlen 4 / 4,5 / 12 bleiben ungeklärt. G0 erfasst tatsächliche Budgets und Zeit. |
| Datenschutz | Produktionsdaten und sensible Prüfunterlagen standardmäßig außerhalb des Repos. Keine Secrets im Workerprompt. |
| Lernen aus Analytics | A12 enthält genau einen nächsten Test und `regel_aenderung: false`. Keine automatische Änderung von Regeln oder Freigaben. |

Eine lokale Bestätigung dokumentiert die Erklärung eines vertrauenswürdigen
Operators. Sie beweist seine Identität oder Qualifikation nicht. Kontexttrennung
zwischen Workerprozessen dokumentiert den zulässigen Informationsfluss, liefert
aber keine harte OS-Leseisolation.
