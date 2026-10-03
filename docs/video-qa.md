# Technische Video- und Untertitelprüfung

Die Prüfer messen lokale Dateien. Sie verändern oder encodieren keine finale
Datei. FFmpeg decodiert beziehungsweise misst in den Null-Muxer; AVC-Header
werden mit Stream-Copy ausgelesen. Alle Prüfungen bleiben an den SHA-256 der
tatsächlich geprüften Bytes gebunden.

## Python-Schnittstellen

```python
from medizinanders.media import inspect_video
from medizinanders.subtitles import generate_srt, validate_srt, GENERATED_TIMING_BASIS

video_report = inspect_video("final.mp4", "qa-reports")
srt_report = validate_srt("final.srt", font_path="Montserrat-Bold.ttf")
estimated_srt = generate_srt(a05_inhalt, a06_inhalt)
```

`inspect_video` liefert `ergebnis`, `checks`, `sha256`, `sha256_after`, `path`,
`profil`, `inspected_at`, `raw_reports`, `manual_steps`, `report_dir`,
`report_path` und `rendered_or_modified: false`. Jeder Aufruf bekommt einen
eigenen Report-Unterordner. `inspection.json` enthält die vollständige Rückgabe.

Jeder Check hat `id`, `status` (`bestanden`, `fehlgeschlagen`,
`nicht_geprueft`), `ist`, `soll`, `grund`. Ein technischer Fehler ergibt
`nacharbeit_erforderlich`. Ohne Fehler, aber mit einer offenen Pflicht ergibt
sich `pruefung_unvollstaendig`. Ungeprüfte Werte werden niemals angenommen.

Rohreports enthalten absolute `path`, Report-`sha256`, `source_sha256`,
`source_unchanged` und die echte Argumentliste `command` sowie Rückgabecode,
Timeout-Status und Fehler. Stdout und Stderr bleiben vollständig erhalten.
Die JSON-Argumentliste ist keine Shell-Befehlszeile. Aufrufe verwenden keine
Shell, absolute Eingabepfade und ein Zeitlimit von 180 Sekunden je Werkzeuglauf.
Ändert sich der Datei-Hash während der Prüfung, sind alle Messungen ungültig.

`validate_srt` liefert dieselben Ergebnis-/Check-Felder, den Hash der echten
SRT-Bytes, `path`, `font_sha256`, geparste `cues`, `timing_basis` und konkrete
`manual_steps`. Eine UTF-8-BOM ist erlaubt; UTF-16 und Latin-1 sind kein UTF-8.
Ein Syntaxfehler verhindert eine erfolgreiche Prüfung des restlichen Dokuments.

## Videoprüfungen

| Check-ID | Nachweis |
| --- | --- |
| `source_readable`, `source_stability` | Lesbarkeit, Dateigröße, SHA-256 vor/nach der gesamten Prüfung. |
| `container_mp4`, `container_faststart` | Echte MP4-Atomgrößen, Marken und top-level Reihenfolge; `moov` vor `mdat`. Die Dateiendung beweist nichts. |
| `stream_count` | Genau eine Video- und eine Audiospur. |
| `video_resolution`, `video_sar` | 1080×1920 ohne wirksame Rotation, SAR 1:1; zusätzlich Eigenschaften jedes wirklich decodierten Frames, damit eine wechselnde SPS nicht hinter dem ersten Streamheader verborgen bleibt. |
| `duration`, `video_frame_count` | Videospur und Container exakt 58 s, genau 1740 wirklich gelesene Frames. |
| `video_cfr` | Jeder originale Frame-PTS gegen `Frameindex/30`, ab 0 s. Toleranz nur halber Timebase-Tick plus 1 µs Rundung. Deklarierte fps und decoderseitige Best-Effort-Zeitstempel ersetzen fehlende PTS nicht. |
| `video_progressive` | Alle echten Frame-Interlace-Flags und widersprechende Field-Order-Metadaten. |
| `video_pixel_format`, `video_color`, `video_codec` | 8-Bit yuv420p an allen Frames, vollständig deklarierte BT.709-Primärfarben/Transfer/Matrix ohne HDR-Side-Data, AVC High Level 4.1. Widersprechende Profil-/Level-/Bitdepth-Werte in späteren echten SPS-Headern werden abgelehnt. |
| `video_gop` | Alle Keyframe-Abstände und Schluss-GOP höchstens 60 Frames; erster Frame Keyframe. |
| `video_closed_gop` | Sämtliche AVC-Headerpakete werden über PTS den Frames zugeordnet. Jede Keyframe-Position muss NAL-Typ 5 (IDR) haben. Unvollständige Header oder fehlendes `trace_headers` bleiben ungeprüft. |
| `video_b_frames` | Echte Bildfolge: kein B-Lauf über zwei, mindestens ein Zweierlauf. `has_b_frames` ist nur Decoder-Reorder-Tiefe und kein Encoder-Nachweis. |
| `video_peak_bitrate` | Höchstens 16 Mbit/s in jedem gleitenden 1-s-Fenster aller Video-Paket-DTS (ersatzweise Paket-PTS), ohne Container-Overhead. Der Endpunkt ist exklusiv. Kein Ersatz für ein VBV-Exportlimit. |
| `decode` | Vollständiges FFmpeg-Decodieren von Bild und Ton mit Fehlerabbruch. |
| `audio_codec`, `audio_sample_rate`, `audio_channels` | AAC-LC, 48.000 Hz, zwei Kanäle mit Stereo-Layout. |
| `audio_loudness` | FFmpeg EBU-R128/BS.1770: integrierte Lautheit der realen finalen Audiospur −15…−13 LUFS. Die letzte präzisere R128-Metadatenmessung wird verwendet. |
| `audio_true_peak` | Oversampled EBU-R128 True Peak höchstens −1,5 dBTP. Die FFmpeg-Summary hat 0,1 dB Präzision: exakt auf −1,5 gerundete Messungen bleiben offen und benötigen einen genaueren Nachweis. |
| `ending_silence` | `atrim`/`astats` messen die vollständigen 54…58 s: 192.000 Samples pro Kanal bei 48 kHz, digitaler Nullpegel. Leiser Restton ist kein Nachweis digitaler Stille. |

Die tatsächlichen Paketmittelraten werden ebenfalls berichtet. Aus einer
mittleren Dateibitrate lassen sich konfigurierte Encoder-Zielraten nicht
zuverlässig rekonstruieren. Folgende Check-IDs benötigen deshalb einen
gesonderten, an die finale Datei-SHA-256 gebundenen Exportprofil-/Encoderbeleg:

- `video_bitrate_target`: Ziel 10 Mbit/s.
- `video_vbv_maxrate`: Encoder-/VBV-Maxrate höchstens 16 Mbit/s.
- `audio_bitrate`: AAC-Ziel 384 kbit/s.

Ein solcher manueller Beleg darf fehlende Auflösungs-, Codec-, CFR-, Decode-
oder andere technische Messungen nicht ersetzen. Der originale Messreport
bleibt unverändert; Freigaben und Nachweise verwaltet der Orchestrator in A10.

`ending_visual_disclaimer` ist eine menschliche Pflicht: alle 54…58 s in
Originalauflösung ansehen und schwarzen Hintergrund, vollständigen korrekten
Disclaimer sowie Lesbarkeit über alle vier Sekunden konkret bestätigen.
`audio_video_sync` verlangt das vollständige Ansehen der finalen Datei mit Ton.
Schwarzer Hintergrund ist trotz heller Disclaimer-Schrift nicht dasselbe wie
ein rein schwarzer Frame; dafür wird kein irreführender Blackdetect-Pass erzeugt.

Fehlen `ffprobe`, `ffmpeg`, Headertracing oder Messfilter, nennt der Report die
offene Prüfung und konkrete Nachholschritte. Nach Installation derselben
Werkzeuge dieselbe finale Datei erneut prüfen und neue Rohreports speichern.
Ein fehlendes Werkzeug darf kein `bestanden` erzeugen.

## Untertitel und geschätzte Timings

`generate_srt` verwendet die A05-`untertitel_basis`, ersatzweise den
`sprechertext`. Vorhandene gesprochene A06-Szenen müssen diesen Text vollständig
abdecken; widersprechender Sprechertext wird nicht ergänzt. Ihre Szenenfenster
liefern ausschließlich **geschätzte redaktionelle Timings**. Ohne Szenenplan
wird zunächst mit 15 CPS innerhalb 0…54 s geschätzt; das ist keine gemessene
Sprechgeschwindigkeit. Eine kurze Zeile wird nicht über 54 Sekunden gestreckt.

Der Caller muss `GENERATED_TIMING_BASIS` sichtbar in den Begleitinformationen
behalten. Standard-SRT enthält nur Untertitel, keine erfundene Synchronmessung
und keinen zusätzlichen, ungesprochenen Hinweis-Text. Zu kurze Szenenfenster,
zu langer Text oder unteilbare Wörter über 28 Zeichen ergeben `ValueError`.
Wörter werden nicht gekürzt oder entfernt. Negation plus folgendes Wort,
Zahlenbereiche, Nenner wie „1 von 100“ und Zahl/Einheit bleiben zusammen.

| Check-ID | Regel |
| --- | --- |
| `srt_utf8`, `srt_syntax`, `srt_index_sequence` | Lesbare UTF-8-Datei, echte SRT-Zeitzeilen, fortlaufend ab 1. |
| `srt_timeline` | Geordnete, positive, nicht überlappende Intervalle vollständig bis höchstens 54,000 s. |
| `srt_line_count`, `srt_line_length` | Höchstens zwei Zeilen, jeweils höchstens 28 Unicode-Zeichen einschließlich Leerzeichen. |
| `srt_cue_duration`, `srt_cps` | 0,80…4,00 s inklusive, höchstens 18 Zeichen/s; Leerzeichen zählen, Zeilenumbrüche nicht. |
| `srt_plain_text` | Keine Styling-Tags oder unsichtbaren Steuerzeichen. |
| `srt_semantic_wrap` | Erkennbare Negations-, Zahlenbereichs- und Einheit-Bindungen bleiben auch über Cue-Grenzen erhalten; redaktionelle Sinnprüfung weiterhin nötig. |
| `srt_pixel_width` | Echte Pillow-Fontlayout-Messung mit **Montserrat Bold 52 px**, höchstens **840 px** pro Zeile. Schriftname/-stil und Hash werden dokumentiert; Ersatzfonts und Zeichenbreiten-Schätzungen zählen nicht. |
| `srt_audio_sync` | Mensch prüft anhand echten finalen Audios, dass Synchronabweichung höchstens 100 ms ist. Aus einer SRT allein unmessbar. |
| `srt_burn_in` | Mensch prüft echte Einbrennung: Montserrat Bold 52 px, x=90…930, y=192…1536, Unterkante höchstens 1520; Quellen y=1200…1320, Lesbarkeit und Quellenkollisionen. |

Fehlen Fontdatei oder Pillow, bleibt Pixelbreite `nicht_geprueft`. Eine korrekte
Fontmessung belegt noch nicht, dass im finalen Video genau dieser Font und
diese Positionen eingebrannt wurden. Audioabgleich und Burn-in bleiben deshalb
auch bei formal perfekten Untertiteln offene menschliche Pflichten.

## Verifikation ohne falsche Produktionsbelege

`tests/test_media.py` erstellt ein eindeutig als **DEMO** benanntes und
metadatiertes 32×64-Testvideo. Die echte technische Prüfung muss Auflösung,
Dauer und Framezahl ablehnen; CFR, IDR und unveränderte Rohreport-Hashes werden
mit vorhandenen FFmpeg-Werkzeugen tatsächlich geprüft. Die Tests erstellen
keinen teuren 1080×1920-Produktionsrender. Die 1740-Frame-Prüfalgorithmen werden
separat mit klar erkennbaren Unit-Rohdaten geprüft. Unit-Daten sind keine
Produktionsnachweise.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_media.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p 'test_subtitles.py' -v
```
