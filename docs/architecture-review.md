# Architekturreview der V1

Stand: 2026-10-03. Review durch den integrierenden Lead Engineer nach dem
vollständigen Aufbau und zusätzlich zum unabhängigen
[Red-Team-Review](red-team-review.md).

## Ergebnis

Die V1 erfüllt den vereinbarten lokalen Aufbau: strukturierte Dateien, native
Codex-Worker, deterministische Prüfungen und explizite menschliche Entscheidungen.
Es gibt keinen Server, Datenbankdienst, eigenen LLM-API-Client oder automatischen
Render-/Uploadpfad. Die Betriebseinrichtung G0 ist beim echten Betreiber offen.

| Gegenstand | Geprüfte Eigenschaft |
|---|---|
| Steuerung | `Pipeline.step()` bestimmt den nächsten zulässigen Worker oder Gate. Ein A02-Import vor G1 wird abgewiesen. Ein normaler Workerimport kann ausschließlich A01–A07 erzeugen. |
| Kontext | Jede Rolle erhält einen eigenen Auftrag mit minimalen Artefakten und konkreten Eingabehashes. ALPHA erhält A01/A02 und Originalbytes, BETA A03 und Produktionsregeln. Änderungen an kopierten Eingaben oder TASK.json blockieren den Import. |
| Fachlichkeit | Claimstatus, Einsatz und genaue Quellenfundstellen werden getrennt geführt. Medizinische und juristische Pflichtreviews bleiben eigenständige Blocker; Agenten dürfen sie nicht bestätigen. |
| Entscheidungen | G0–G5b werden ausschließlich durch konkrete Operatorerklärungen gesetzt. Die CLI verlangt eine interaktive Bestätigungszeile; simulierte Testentscheidungen sind ausschließlich DEMO beziehungsweise Testadapter. |
| Versionen | Alte Dateien bleiben erhalten. G1/G2 zeigen bereits die zu bestätigenden 1.0.0-Versionen und ihre vorberechneten Hashes. Neue Fassungen erben keine Freigabe. |
| Freeze | Jede Revision besitzt A01–A07, Rechteverweise, Manifest und SHA256SUMS. Die Prüfung verlangt die vollständige Pflichtmenge und vergleicht Kopien, aktuelle Artefakte, Projekt, DEMO-Kennung und Regeln. Freigaben liegen außerhalb des Freeze. |
| Handoffs | Inhalt und Vollständigkeit werden gegen deterministisch aus den Artefakten erzeugte Dateien geprüft. Ein veränderter Sprechertext oder Uploadtitel kann nicht durch erneutes Abhaken gültig werden. |
| Medien | FFmpeg prüft reale Bytes, einschließlich vollständigem Decode und Loudness. Fehlgeschlagene Messungen bleiben blockierend. Nur fünf ausdrücklich benannte unmessbare Eigenschaften erlauben ergänzende menschliche Nachweise; Rohreports bleiben erhalten. |
| Rückwege | Quellen/Bedeutung führen zu ALPHA und erneutem G2. Wortlaut führt zu BETA/QA. Ein Ersatzexport erhält unveränderte G4-Vorschauprüfungen, entwertet aber Finalprüfungen und G5a/G5b. |
| Plattform | Private Upload- und Veröffentlichungsrückmeldungen sind menschliche Erklärungen zu konkreten Hashes und IDs. Ein neuer Upload benötigt neues Playback und G5b. Alte Records werden archiviert. |
| Analytics | A12 gehört zur aktuellen dokumentierten Veröffentlichung. Fehlende Metriken bleiben null mit Grund; Beobachtung und Hypothese bleiben getrennt, genau ein nächster Test, keine automatische Regeländerung. |
| Datenschutz | Produktionsspeicher liegt außerhalb des Repos. Rekursive Ignore-Regeln und ein Dateityp-/Secret-Check schützen zusätzlich gegen versehentlich kopierte Projektunterlagen. |

## Nachweis und praktische Grenzen

[Verifikation](verification.md) dokumentiert den abschließenden Testlauf, den
synthetischen vollständigen Dry Run und einen tatsächlichen isolierten nativen
GAMMA-Lauf. Der unabhängige Reviewer reproduzierte elf Fehler, prüfte deren
Korrekturen und meldete keine offenen Codebefunde.

Kontexttrennung ist keine OS-Leseisolation. Ein vertrauenswürdiger lokaler
Operator kann Dateien bewusst verändern; Hashes und Logs ersetzen weder eine
Identitätsprüfung noch einen wissenschaftlichen, medizinischen oder juristischen
Nachweis. Quellenbytes beweisen den konkreten Prüfgegenstand, nicht die Wahrheit
eines Claims. V1 behauptet keine C2PA-Verifikation.

Die hier vorhandene Codex CLI meldete beim tatsächlichen Lauf HTTP 401. Native
Subagents mit frischem Kontext und registrierter Dateiübergabe wurden dagegen
erfolgreich genutzt. Ein vollständiger produktiver Research-/Videolauf wird erst
mit funktionierender Betreiberanmeldung und realen Quellen/Medien nachgewiesen.
Das Anlegen und die Sichtbarkeitsänderung des GitHub-Repositories wurden vom
verfügbaren Zugriff mit HTTP 403 abgewiesen. Der Betreiber legte das Remote
selbst an und autorisierte ausdrücklich einen öffentlichen Push; die spätere
Umstellung auf privat übernimmt er selbst.

Es wurde kein echtes Human Gate gesetzt, kein Kostenauftrag akzeptiert, kein
InVideo-Render erzeugt und kein YouTube-Upload oder Veröffentlichungsaufruf
ausgeführt. Die echten Fach-, Rechte-, Smartphone-, Hör- und Plattformprüfungen
bleiben beim Betreiber beziehungsweise den realen Fachpersonen.
