# Manuelle Schritte

Die CLI koordiniert Entwürfe, Nachweise und Gates. Sie bedient InVideo und
YouTube nicht. Tatsächlicher Render, Rechteklärung, Fachreview, Upload,
Plattformverarbeitung und Veröffentlichung bleiben konkrete Operatorhandlungen.

## Umgebung vorbereiten

`ma doctor` zeigt, welche lokalen Programme und nativen Codex-Fähigkeiten
vorhanden sind. Mit `ma setup` eine lokale Konfiguration außerhalb des Repos
anlegen und reale Toolmöglichkeiten, Speicher, Datenschutz, Ressourcen, Zielgruppe
und Stimme eintragen. Männliche Stimme ist ein Vorschlag und muss ausdrücklich
gewählt werden. Ein Text in der Konfiguration beweist nicht, dass InVideo etwa
getrennte Audiotracks, das gewünschte Font oder den vollständigen Exportcodec
unterstützt. Diese Möglichkeiten vor G0 tatsächlich prüfen.

## Quellen und fachliche Prüfung

Originalquellen öffnen, konkrete Fundstellen sichern und Snapshots im
Projektspeicher behalten. Ein Snippet oder eine KI-Zusammenfassung reicht nicht.
Abrufprobleme, fehlende Studienparameter, Korrekturen und widersprüchliche
Ergebnisse dokumentieren. Bei Reviewbedarf die claimbezogenen Pakete unter
`review/` an einen geeigneten menschlichen Prüfer geben, echte Entscheidungen
über `ma review` registrieren und erforderliche Änderungen vor G2 einarbeiten.

## Nach G3: InVideo-Handoff

1. Die acht Inhaltsdateien unter `handoff/invideo/` vollständig lesen. Freeze, Wortlaut und
   Szenenzeiten mit dem freigegebenen Stand abgleichen.
2. InVideo manuell konfigurieren: Deutsch, ausdrücklich gewählte ruhige Stimme,
   keine imitierte Person, 9:16, festes 58-Sekunden-Profil und geklärte Assets.
3. Freigegebenen Sprechertext unverändert verwenden. Untertitel, Overlays und
   Quellenhinweise aus den Handoff-Dateien übernehmen. Automatische Umschreibungen
   oder zusätzliche Fakten entfernen beziehungsweise in die Redaktion zurückführen.
4. Den harten Schnitt bei 3 Sekunden, genau einen CTA und den schwarzen stillen
   Disclaimer von 54 bis 58 Sekunden herstellen. Keine automatische Musikauswahl
   mit Gesang oder dramatischen Stings übernehmen.
5. Preview nach `08_produktion/inbox/preview.mp4` exportieren. Es ist ein echter
   Render, kein Platzhalter. Technische QA ausführen und das ganze Video sehen
   und hören; das tatsächliche Previewattest über `ma attest` bestätigen.
6. Erst nach G4 notwendige Korrekturen am Final produzieren. Neue Fakten, neue
   Formulierungen oder andere Assets über den passenden Rückweg behandeln.
7. `final.mp4` und `subtitles.srt` im gleichen Inbox-Verzeichnis ablegen.
   Getrennte Sprach-/Musikspuren sichern, wenn Musik verwendet wird; ohne verlässlich
   messbare Trennung Musik entfernen. Final-QA und menschlichen Finalcheck durchführen.

`EXPECTED_OUTPUT.md` enthält die vollständigen Codec-, Audio-, Untertitel- und
Timingvorgaben. Kann InVideo sie nicht zuverlässig liefern, sind ein geeigneter
manueller Exportschritt und erneute Prüfung nötig. Ein unprüfbarer Wert bleibt
`nicht_geprueft`; weder ein Prompt noch ein gesetztes Flag beweist seine Einhaltung.

Die ungeprüften Vorlagen `handoff/invideo/PREVIEW_CHECKLIST.example.json` und
`FINAL_CHECKLIST.example.json` in eigene `PREVIEW_CHECKLIST.json` und
`FINAL_CHECKLIST.json` kopieren. Den tatsächlichen Operator, Zeitpunkt, Freeze,
aktuellen Medienhash und konkrete Nachweise eintragen; `example` bleibt bei einer
echten Erklärung nicht `true`. Nur persönlich geprüfte Punkte bestätigen.
Die Previewerklärung verlangt zusätzlich `render_invideo: true` ausschließlich
nach dem tatsächlichen InVideo-Render; ein synthetisches Testvideo erfüllt das nicht.

## Privater Upload und Veröffentlichung

1. Vor G5a KI-Kennzeichnung, Zielgruppe und Werbung bewusst festlegen. Titel,
   Thumbnail und Beschreibung bleiben claimgebundene öffentliche Aussagen.
   `handoff/youtube/YOUTUBE_DECISIONS.example.json` dafür als eigene
   `YOUTUBE_DECISIONS.json` ausfüllen; die Vorlage ist keine Entscheidung.
2. Nach G5a das geprüfte Finalvideo manuell privat auf YouTube hochladen und die
   freigegebenen Metadaten sowie SRT übertragen.
3. Den tatsächlichen Upload mit `ma youtube private <ID> --id <YOUTUBE_ID>
   --url <URL>` registrieren. Auf abgeschlossene Verarbeitung warten.
4. Das verarbeitete private Video vollständig abspielen, Bild, Ton, Untertitel,
   Synchronität, Quellen und Disclaimer prüfen. Playbackattest über `ma attest`
   registrieren und erst danach G5b entscheiden.
   Dafür `handoff/playback/PLAYBACK_CHECKLIST.example.json` als eigene
   `PLAYBACK_CHECKLIST.json` mit echter Video-ID/URL und Nachweisen ausfüllen.
5. Die Sichtbarkeit manuell öffentlich setzen und mit
   `ma youtube published <ID> --url <URL>` den tatsächlichen veröffentlichten
   Stand dokumentieren. Die CLI veröffentlicht nicht selbst.

## Analytics

Reale Messdaten mit Zeitraum und Quelle sammeln und über `ma analytics` einlesen.
Fehlende Zahlen als fehlend mit Begründung führen, keine Erfolgswerte ergänzen.
A12 trennt Beobachtungen von Hypothesen und schlägt genau einen nächsten Test vor.
Ein Testvorschlag verändert redaktionelle Regeln oder veröffentlichte Inhalte nicht.

Gib Codex den tatsächlichen Export und diesen Arbeitsauftrag:

> Erstelle außerhalb des Repos eine analytics.json zur aktuell veröffentlichten
> Episode. Verwende ausschließlich meinen tatsächlichen Export. Dokumentiere
> Datenquelle und Zeitraum. Trenne beobachtete Zahlen von Hypothesen. Setze
> fehlende Metriken auf null mit einer konkreten Begründung. Formuliere genau
> einen überprüfbaren nächsten Test. Erfinde keine Plattformmetriken oder Werte.

Der Import nimmt die folgenden sechs Felder entgegen; er fügt die
Artefaktmetadaten selbst hinzu. Diese leere **Strukturvorlage** enthält keine
Messung und darf erst nach Ergänzung der tatsächlichen Quelle/Periode verwendet
werden:

```json
{
  "datenquelle": "Tatsächlichen lokalen Export und Video-ID eintragen",
  "zeitraum": "Tatsächliche Start-/Endzeit eintragen",
  "metriken": {
    "views": {"wert": null, "begruendung": "Im bereitgestellten Export nicht verfügbar"},
    "average_percentage_viewed": {"wert": null, "begruendung": "Im bereitgestellten Export nicht verfügbar"}
  },
  "beobachtungen": [],
  "hypothesen": [],
  "naechster_test": "Genau einen Test mit Variable, Vergleich, Messgröße und Beobachtungszeitraum formulieren"
}
```

`ma analytics <ID> --file /privater/pfad/analytics.json` setzt fehlende Standard-
metriken einschließlich Swipe-Away ausdrücklich auf null mit Grund; eine
Plattformmetrik wird nicht allein dadurch als verfügbar behauptet. Der
Orchestrator bindet A12 an den aktuellen tatsächlichen A11-Publikationsstand.
