"""Synthetic, local examples. Nothing in this module approves production work."""

from __future__ import annotations

import copy
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from .errors import PipelineError
from .util import digest, load_json, write_json


DEMO_TOPIC = "DEMO: Ein Papierstern im fiktiven Archiv"
DEMO_DATE = "2026-01-01T12:00:00+00:00"
DISCLAIMER = "Journalistischer Analyse-Content. Kein medizinischer Rat."
SOURCE_ID = "SRC-DEMO-001"
CLAIM_ID = "C-DEMO-001"
ORIGINAL_PATH = "sources/demo_original.txt"
ORIGINAL_TEXT = (
    "DEMO – vollständig synthetisches Original\n"
    "Titel: Der Papierstern im fiktiven Archiv\n"
    "\n"
    "Ein Stern aus Papier liegt im Archiv.\n"
    "\n"
    "Dieses lokal erstellte Beispiel beschreibt keine wirkliche Sammlung, "
    "keine Person und keinen medizinischen Sachverhalt. Die Beispieladresse "
    "https://example.invalid/DEMO/papierstern wurde nicht abgerufen. "
    "Der Satz über den Papierstern ist Teil dieser erfundenen Quelle.\n"
)
ORIGINAL_BYTES = ORIGINAL_TEXT.encode("utf-8")
ORIGINAL_SHA256 = hashlib.sha256(ORIGINAL_BYTES).hexdigest()
ASSET_PATH = "sources/demo_paperstar.svg"
ASSET_BYTES = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" '
    'viewBox="0 0 1080 1920"><rect width="1080" height="1920" fill="#173044"/>'
    '<polygon points="540,550 610,770 845,770 655,910 725,1130 '
    '540,995 355,1130 425,910 235,770 470,770" fill="#fff1bd"/>'
    '<text x="540" y="1300" text-anchor="middle" fill="white" '
    'font-size="72">DEMO</text></svg>\n'
).encode("utf-8")
RIGHTS_PATH = "sources/demo_assets_rights.txt"
RIGHTS_BYTES = (
    "DEMO-Nachweis: demo_paperstar.svg ist eine lokal aus einfachen SVG-Formen "
    "erstellte synthetische Grafik dieser Demo. Kein Fremdmaterial, keine "
    "erkennbare Person, keine imitierte Stimme und keine Musik. "
    "Dieser Nachweis gilt nur für die DEMO-Fixture.\n"
).encode("utf-8")
DEMO_OPERATOR = "DEMO-SIMULATION – fiktiver Operator"

SECTIONS = (
    ("Hook", 0, 3000, ("Stell dir ein Archiv vor.",)),
    (
        "Open Loop", 3000, 8000,
        ("Denk an einen Stern aus Papier, ganz ohne große Welt.",),
    ),
    (
        "Payload", 8000, 41000,
        (
            "Im fiktiven DEMO-Text steht: Ein Stern aus Papier liegt im Archiv.",
            "Lies den Satz in Ruhe und prüfe jedes Wort.",
            "Frag dich, was dort steht, was fehlt und was du nur dazu denkst.",
            "Nimm den Stern als Bild für eine kleine Spur.",
            "Halte Text und Deutung klar im Blick.",
            "Gib dem stillen Bild Zeit und lass Raum für Zweifel.",
            "Sag nur, was der Text hergibt, und bleib bei ihm.",
        ),
    ),
    (
        "Verdichtung", 41000, 48000,
        ("Zieh den Blick nun eng: Ein Satz, ein Bild, ein klarer Rand.",),
    ),
    ("CTA", 48000, 52000, ("Schau dir das DEMO-Original an.",)),
    ("Ausklang", 52000, 54000, ("Lass den Stern nun ruhen.",)),
    ("Disclaimer", 54000, 58000, ("",)),
)


def prepare_sources(project_path: Path) -> None:
    """Create and read the actual synthetic evidence without replacing files."""
    root = Path(project_path)
    for relative, payload in (
        (ORIGINAL_PATH, ORIGINAL_BYTES),
        (ASSET_PATH, ASSET_BYTES),
        (RIGHTS_PATH, RIGHTS_BYTES),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise PipelineError(f"DEMO-Nachweis wurde verändert: {relative}")
        else:
            with path.open("xb") as stream:
                stream.write(payload)
        if path.read_bytes() != payload:
            raise PipelineError(f"DEMO-Nachweis stimmt nicht: {relative}")


def _statement(text: str, factual: bool = False) -> dict[str, Any]:
    return {"text": text, "faktisch": factual, "claim_ids": [CLAIM_ID] if factual else []}


def _invideo_prompt(script: str) -> str:
    sections = "\n".join(
        f"{start / 1000:g}–{end / 1000:g} s, {function}: "
        f"{DISCLAIMER if function == 'Disclaimer' else ' '.join(sentences)}"
        for function, start, end, sentences in SECTIONS
    )
    return (
        "DEMO_SIMULATION – vollständig synthetischer manueller InVideo-Handoff. "
        "Dieser Prompt belegt keinen InVideo-Aufruf und keinen Render.\n"
        "Erzeuge ausschließlich die erfundene Papierstern-Szene mit sichtbarem DEMO-Hinweis. "
        "Keine Patientendaten, klinischen Behauptungen, echten Archivaufnahmen, "
        "medizinischen Autoritäten oder Personen. Nutze nur die selbst erstellte "
        f"Grafik {ASSET_PATH}; Rechtebeleg {RIGHTS_PATH}.\n"
        "Profil MA-SHORT-58-v1.0: 1080x1920, 9:16, exakt 58,000 Sekunden, "
        "30 fps konstant, 1740 Frames, progressiv, SAR 1:1, yuv420p, BT.709 SDR. "
        "MP4 mit fast start; H.264/AVC High, Level 4.1, Closed GOP maximal "
        "60 Frames, 2 B-Frames, Zielbitrate 10 Mbit/s, maximal 16 Mbit/s.\n"
        "Ruhige erwachsene deutsche Stimme, keine imitierte Person. "
        "Voiceover von 0 bis 54 s; von 54 bis 58 s ausschließlich der visuelle "
        "Disclaimer ohne Voiceover und Musik. "
        "Keine Musik. AAC-LC, 48 kHz, Stereo, Ziel 384 kbit/s, "
        "-14 LUFS (zulässig -15 bis -13), True Peak maximal -1,5 dBTP. "
        "Die Audiopegel müssen am tatsächlichen Render gemessen werden.\n"
        "Untertitel: UTF-8-SRT und eingebrannt, Montserrat Bold, 52 px, weiß, "
        "höchstens 2 Zeilen, höchstens 28 Zeichen je Zeile, höchstens 18 CPS, "
        "800–4000 ms je Cue und höchstens 100 ms Syncabweichung. "
        "Safe area x=90–930, y=192–1536, Unterkante 1520; "
        "Quellenhinweis y=1200–1320. Schriftbreite tatsächlich prüfen.\n"
        "Hook-Schnitt bei 3 s. Alle Übergänge ruhig; keine Stings oder fremden Assets. "
        "Genau eine CTA im Segment 48–52 s. Fester Disclaimer bleibt unverändert.\n"
        "Von 54 bis 58 s ausschließlich schwarzer Hintergrund und weißer Disclaimer; "
        "keine weiteren Bilder, Untertitel, DEMO-Logos oder Quellenhinweise.\n"
        f"Quelle: {SOURCE_ID}, fiktives lokales DEMO-Original, Absatz 1. "
        "Der Papierstern ist nur eine Quellenbehauptung innerhalb dieser Fiktion.\n"
        f"Wortgetreuer Sprechertext (ohne separaten Disclaimer): {script}\n"
        f"Zeitplan:\n{sections}\n"
        "Keinen Render als freigegeben bezeichnen. Manuell exportieren und "
        "anschließend die echte Datei technisch sowie durch Menschen prüfen."
    )


def fixtures(project_id: str) -> dict[str, dict[str, Any]]:
    """Return fresh A01–A07 worker artifacts containing only DEMO evidence."""
    speech_sections = SECTIONS[:-1]
    script = " ".join(sentence for _, _, _, texts in speech_sections for sentence in texts)
    source_claim = speech_sections[2][3][0]
    sentences = []
    for function, _, _, texts in speech_sections:
        for sentence in texts:
            sentences.append({
                "id": f"S-DEMO-{len(sentences) + 1:03}",
                **_statement(sentence, sentence == source_claim),
                "funktion": function,
            })
    contents: dict[str, dict[str, Any]] = {
        "A01": {
            "kernfrage": "Wie wird ein Satz aus einem erfundenen DEMO-Original nachvollziehbar?",
            "nutzen": "Die lokalen Artefakte, Quellenbindungen und Gates an einer Fiktion zeigen.",
            "scope": ["DEMO: fiktiver Papierstern", "Ausschließlich synthetische lokale Originalbytes"],
            "ausschluesse": ["Medizinische Aussagen", "Patientendaten", "Echte Veröffentlichung", "Reale Recherche"],
            "suchfragen": ["Steht der Papierstern-Satz tatsächlich im lokalen DEMO-Original?"],
            "format": "MA-SHORT-58-v1.0",
            "ressourcen": {"budget_eur": 0, "zeit_minuten": 10, "stimme": "synthetisches DEMO-Beispiel"},
            "offene_entscheidungen": [],
        },
        "A02": {
            "sources": [{
                "id": SOURCE_ID,
                "url": "https://example.invalid/DEMO/papierstern",
                "titel": "DEMO: Der Papierstern im fiktiven Archiv",
                "typ": "synthetisches lokales DEMO-Original",
                "zugriff": "geprueft",
                "fundstelle": "Absatz 1: Ein Stern aus Papier liegt im Archiv.",
                "abgerufen_am": DEMO_DATE,
                "sha256": ORIGINAL_SHA256,
                "original_geoeffnet": True,
                "lokaler_pfad": Path(ORIGINAL_PATH).name,
                "klinische_parameter": {
                    key: None for key in (
                        "population", "design", "vergleich", "endpunkt",
                        "absolute_wirkung", "relative_wirkung", "unsicherheit",
                        "interessenkonflikte", "grenzen",
                    )
                },
            }],
            "suchprotokoll": [{
                "frage": "DEMO: Enthält das selbst erstellte lokale Original den Papierstern-Satz?",
                "weg": ORIGINAL_PATH,
                "ergebnis": "Originalbytes lokal geöffnet; keine Online-Recherche oder URL-Abfrage.",
            }],
            "gegenbelege": ["Keine realen Sachverhalte geprüft; die Quelle selbst bezeichnet die Szene als erfunden."],
            "korrekturen_retraktionen": [],
        },
        "A03": {
            "claims": [{
                "id": CLAIM_ID,
                "text": source_claim,
                "status": "BESTÄTIGT",
                "einsatz": "ja",
                "source_ids": [SOURCE_ID],
                "fundstellen": ["Absatz 1: Ein Stern aus Papier liegt im Archiv."],
                "gegenbelege": [],
                "einschraenkungen": ["Nur Aussage über den Inhalt einer erfundenen DEMO-Quelle; kein realer Archivfund."],
                "risiken": [],
                "medizinisch_relevant": False,
                "rechtlich_relevant": False,
                "art": "quellenbehauptung",
            }],
            "faktenmatrix": [{"claim_id": CLAIM_ID, "nachweis": f"{SOURCE_ID}, Absatz 1", "demogrenze": "synthetisch"}],
            "risikoübersicht": [],
            "psychologie_map": [{"funktion": "Aufmerksamkeit", "mittel": "Fiktives ruhiges Papierstern-Bild ohne Drohung oder Heilsversprechen"}],
            "medical_review_required": False,
            "legal_review_required": False,
        },
        "A04": {
            "profil": "MA-SHORT-58-v1.0",
            "abschnitte": [
                {"funktion": function, "start_ms": start, "ende_ms": end}
                for function, start, end, _ in SECTIONS
            ],
            "dramaturgie": "DEMO: ruhiger Einstieg, eine fiktive Quellenbehauptung, Textprüfung, eine CTA, separater Disclaimer.",
            "cta_anzahl": 1,
        },
        "A05": {
            "sprechertext": script,
            "wortzahl": len(script.split()),
            "saetze": sentences,
            "untertitel_basis": script,
            "aussprache": ["DEMO: Demo; keine Namen echter Personen"],
            "overlays": [
                {**_statement("DEMO – synthetisch"), "start_ms": 0, "ende_ms": 8000},
                {
                    **_statement("DEMO: Im fiktiven Text liegt ein Papierstern im Archiv.", True),
                    "start_ms": 8000,
                    "ende_ms": 41000,
                },
                {**_statement("DEMO – synthetisch"), "start_ms": 41000, "ende_ms": 54000},
            ],
            "titel": _statement("DEMO: Lies den Papierstern-Satz"),
            "thumbnail": _statement("DEMO – denk dir ein Archiv"),
            "beschreibung": _statement("DEMO: Im erfundenen Original liegt ein Stern aus Papier im Archiv.", True),
            "quellenangaben": [f"{SOURCE_ID}: synthetisches lokales DEMO-Original, {ORIGINAL_PATH}, Absatz 1"],
            "cta": _statement(speech_sections[4][3][0]),
            "disclaimer": DISCLAIMER,
        },
        "A06": {
            "szenen": [
                {
                    "id": f"SC-DEMO-{index:03}",
                    "start_ms": start,
                    "ende_ms": end,
                    "sprechertext": " ".join(texts),
                    "funktion": function,
                    "motiv": (
                        "Ausschließlich schwarzer Hintergrund und weißer fixer Disclaimer; keine weiteren Elemente"
                        if function == "Disclaimer" else
                        "Synthetische eigene Papierstern-Grafik mit sichtbarem DEMO-Hinweis"
                    ),
                    "assets": [] if function == "Disclaimer" else ["ASSET-DEMO-001"],
                    "sync_anker": f"{start} ms: {texts[0]}" if function != "Disclaimer" else "54000 ms: stummes Disclaimerbild",
                    "overlay": (
                        DISCLAIMER if function == "Disclaimer" else
                        "DEMO: Im fiktiven Text liegt ein Papierstern im Archiv." if function == "Payload" else
                        "DEMO – synthetisch"
                    ),
                    "quellenhinweis": (
                        "" if function == "Disclaimer" else
                        f"{SOURCE_ID}: fiktives DEMO-Original, Absatz 1" if function == "Payload" else
                        "DEMO – synthetisch"
                    ),
                    "uebergang": (
                        "harter Schnitt" if start == 3000 else
                        "Unverändert bis Videoende stehen lassen" if function == "Disclaimer" else
                        "Ruhiger Schnitt"
                    ),
                    "audio": {"voiceover": function != "Disclaimer", "musik": False},
                    "claim_ids": [CLAIM_ID] if function == "Payload" else [],
                }
                for index, (function, start, end, texts) in enumerate(SECTIONS, start=1)
            ],
            "assets": [{
                "id": "ASSET-DEMO-001",
                "typ": "eigene SVG-Grafik",
                "herkunft": ASSET_PATH,
                "recht_status": "geklaert",
                "nachweis": RIGHTS_PATH,
                "ki_illustration": False,
                "imitierte_stimme": False,
            }],
            "invideo_prompt": _invideo_prompt(script),
        },
        "A07": {
            "ergebnis": "freigabefaehig",
            "findings": [],
            "pflichtpruefungen": [
                {
                    "id": identifier,
                    "anwendbar": True,
                    "erledigt": True,
                    "nachweis": evidence,
                }
                for identifier, evidence in (
                    ("claim_sentence_map", f"DEMO-Fixture: Der einzige faktische Satz sowie Overlay und Beschreibung binden {CLAIM_ID}; Szenentext stimmt mit A05 überein."),
                    ("sources_originals", f"DEMO-Fixture: {ORIGINAL_PATH} ist das selbst erstellte Original; Fundstelle enthält den Satz und SHA-256 wird aus exakt diesen UTF-8-Bytes gebildet."),
                    ("counterevidence_uncertainty", "DEMO-Fixture: A02 dokumentiert die Fiktion; A03 begrenzt die bestätigte Aussage auf den Quelleninhalt. Keine Aussage über einen realen Archivfund."),
                    ("medical_legal_escalation", "DEMO-Fixture: Der Quellenclaim enthält keine Medizin, Personen oder Rechtsfrage; beide claimbezogenen Relevanzfelder und Reviewpflichten sind false."),
                    ("timeline_cta_disclaimer", f"DEMO-Fixture: 7 lückenlose Abschnitte 0–58 s, {len(script.split())} Wörter bis 54 s, genau eine CTA 48–52 s und separater fester Disclaimer 54–58 s."),
                    ("assets_rights", f"DEMO-Fixture: Einfache eigene SVG-Formen in {ASSET_PATH}; lokaler Eigenherstellungsnachweis {RIGHTS_PATH}; keine Musik oder imitierte Stimme."),
                    ("invideo_complete", "DEMO-Fixture: A06-Prompt nennt Bild- und Audioformat, Zeitplan, wortgetreuen Text, Untertitel, Safe area, Rechte, CTA, Disclaimer und manuellen Export. Ein tatsächlicher InVideo-Render ist offen."),
                )
            ],
            "freeze": None,
        },
    }
    return {
        artifact_id: {
            "artefakt_id": artifact_id,
            "projekt_id": project_id,
            "version": "0.1.0",
            "datum": DEMO_DATE,
            "autor": "DEMO – synthetische Worker-Fixture",
            "status": "Entwurf",
            "eingaben": [],
            "quellen": [] if artifact_id == "A01" else [SOURCE_ID],
            "offene_punkte": [],
            "gesperrt": False,
            "sperrgrund": None,
            "beispiel": True,
            "inhalt": copy.deepcopy(content),
        }
        for artifact_id, content in contents.items()
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineError(f"DEMO-Prüfung fehlgeschlagen: {message}")


def _simulation_confirmation(prompt: str) -> str:
    """Only the isolated demo calls this synthetic confirmation callback."""
    lines = [line.removeprefix("Eingabe: ") for line in prompt.splitlines() if line.startswith("Eingabe: ")]
    if len(lines) != 1:
        raise PipelineError("DEMO-Simulation benötigt eine eindeutige Bestätigungsphrase.")
    return lines[0]


def _configure_demo(pipeline: Any) -> None:
    path = pipeline.setup()
    config = pipeline.config()
    if config.get("verantwortliche_person") not in (None, DEMO_OPERATOR):
        raise PipelineError("DEMO-Speicher enthält eine andere Betreiberkonfiguration; sie wird nicht verändert.")
    config.update({
        "verantwortliche_person": DEMO_OPERATOR,
        "umgebung": "DEMO: isolierte lokale synthetische Simulation",
        "invideo_moeglichkeiten": "DEMO: ausschließlich ein vorbereiteter manueller Handoff; kein InVideo-Aufruf",
        "zielgruppe": "DEMO: fiktives erwachsenes Testpublikum",
        "stimme": "DEMO: keine tatsächlich gerenderte Stimme",
        "budget_eur": 1,
        "zeitlimit_minuten": 10,
        "font_path": None,
        "demo_simulation": True,
    })
    for key in (
        "datenschutz_bestaetigt", "rollenprompts_geprueft", "speicherort_bestaetigt",
        "tools_geprueft", "codex_nutzung_bestaetigt", "research_web_bestaetigt",
    ):
        config[key] = True
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)


def _negative_video(project_path: Path) -> Path:
    """Encode real test bytes with a visible DEMO label and wrong resolution."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        raise PipelineError("DEMO --with-video benötigt tatsächlich installiertes ffmpeg und ffprobe.")
    directory = Path(project_path) / "demo_media"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    label = directory / "negative_label.txt"
    label.write_text("DEMO\nSYNTHETISCH\nNEGATIVTEST 320x568", encoding="utf-8")
    target = directory / "DEMO_NEGATIVE_320x568.mp4"
    if target.exists():
        raise PipelineError("Die DEMO-Testdatei wird nicht überschrieben.")
    # Run with a controlled cwd so drawtext only needs a fixed relative filename.
    drawtext = "drawtext=textfile=negative_label.txt:fontcolor=white:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2"
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-n",
        "-f", "lavfi", "-i", "color=c=0x173044:s=320x568:r=30:d=58",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
        "-t", "58", "-movflags", "+faststart", target.name,
    ]
    try:
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError(f"Die echte DEMO-Testdatei konnte nicht erzeugt werden: {exc}") from exc
    if result.returncode or not target.is_file():
        raise PipelineError("ffmpeg konnte die markierte DEMO-Testdatei nicht erzeugen: " + result.stderr[-1000:])
    return target


def _clean(value: Any, project_path: Path, demo_home: Path, repo: Path) -> Any:
    """Remove machine paths from a showcase snapshot without copying private logs."""
    if isinstance(value, dict):
        return {key: _clean(child, project_path, demo_home, repo) for key, child in value.items()}
    if isinstance(value, list):
        return [_clean(child, project_path, demo_home, repo) for child in value]
    if isinstance(value, str):
        for path, label in ((project_path, "<DEMO_PROJECT>"), (demo_home, "<DEMO_HOME>"), (repo, "<REPO>")):
            value = value.replace(str(path), label)
        return value
    return value


def _snapshot(pipeline: Any, pid: str, result: dict[str, Any], original_versions: dict[str, str]) -> Path:
    root = pipeline.project(pid)
    target = pipeline.repo / "demo" / "output" / f"{pid}-{uuid4().hex[:8]}"
    target.mkdir(parents=True, mode=0o700)
    candidates = []
    for folder in ("artifacts", "freeze", "handoff/invideo", "workers/DEMO"):
        candidates.extend(path for path in (root / folder).rglob("*") if path.is_file())
    candidates.extend(root / relative for relative in (ORIGINAL_PATH, ASSET_PATH, RIGHTS_PATH, "brief.json"))
    if result["media"] is not None:
        candidates.append(root / "08_produktion/inbox/preview.mp4")
    for source in candidates:
        relative = source.relative_to(root)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = source.read_bytes()
        if source.suffix in (".txt", ".md"):
            text = payload.decode("utf-8")
            text = _clean(text, root, pipeline.home, pipeline.repo)
            payload = text.encode("utf-8")
        destination.write_bytes(payload)
    for gate, reference in pipeline.state(pid)["approvals"].items():
        record = load_json(root / reference["path"])
        _require(record["kind"] == "DEMO_SIMULATION", f"{gate} ist keine Simulation.")
        destination = target / reference["path"]
        write_json(destination, record, exclusive=True)
    write_json(target / "G0.demo.json", load_json(pipeline.home / "G0.demo.json"), exclusive=True)
    write_json(target / "DEMO_RESULT.json", {
        **_clean(result, root, pipeline.home, pipeline.repo),
        "report_path": "REPORT.md",
        "snapshot_path": ".",
    }, exclusive=True)
    versions = "\n".join(
        f"| {aid} | `artifacts/{aid}/v0.1.0.json` | `{fingerprint}` |"
        for aid, fingerprint in sorted(original_versions.items())
    )
    media = result["media"]
    media_text = (
        "Optionaler realer Medien-Negativtest: nicht angefordert."
        if media is None else
        "Optionaler realer Medien-Negativtest: 58 Sekunden, sichtbar DEMO, "
        "320 × 568 Pixel statt 1080 × 1920. Ergebnis: " + str(media["ergebnis"]) + ". "
        "Die Auflösungsprüfung meldet tatsächlich fehlgeschlagen. "
        "Diese Datei stammt aus ffmpeg und ist kein InVideo-Render."
    )
    checks = [
        ("Kennzeichnung", "A01–A07 enthalten beispiel=true; sämtliche Inhalte sind erfunden."),
        ("Speicher", "Eigenes DEMO-Verzeichnis; produktive Betreiberkonfiguration und G0 bleiben unberührt."),
        ("G0", "Nur DEMO_SIMULATION; Bereitschaftsangaben und Budget sind fiktive Testwerte."),
        ("GAMMA", "A01 als Worker-Ergebnis importiert; Themenauftrag bleibt synthetisch."),
        ("Rechercheblockade", "Ein A02-Import vor G1 wurde tatsächlich abgewiesen."),
        ("G1/Versionen", "Simuliertes G1 erzeugt A01 v1.0.0; die ursprünglichen Entwürfe bleiben bytegleich."),
        ("RESEARCH", f"{SOURCE_ID}: tatsächliche lokale Originalbytes, Fundstelle und SHA-256; keine URL-Abfrage."),
        ("ALPHA", f"{CLAIM_ID} bestätigt ausschließlich den Inhalt der erfundenen Quelle."),
        ("G2/Reviews", "Simuliertes G2; keine medizinischen/rechtlichen Reviewpflichten und keine erfundenen Fachentscheidungen."),
        ("BETA", "106 Wörter; genaue 58-s-Timeline, eine CTA, separater stummer Disclaimer, eigene SVG mit Rechtebeleg."),
        ("QA-RED-TEAM", "A07 mit sieben spezifischen Pflichtprüfungen importiert; strukturelle und semantische Bundleprüfung durchgeführt."),
        ("Freeze/Handoff", "Freeze-Manifest und Datei-Hashes geprüft; vollständiger manueller InVideo-Handoff und geschätzte SRT vorbereitet."),
        (
            "Ehrlicher Stopp",
            f"WAITING_FOR_HUMAN/{result['next']['gate']}: "
            "echtes InVideo-Rendering unbestätigt; G4, G5a und G5b tatsächlich blockiert.",
        ),
    ]
    checklist = "\n".join(f"| {index} | {name} | {evidence} |" for index, (name, evidence) in enumerate(checks, 1))
    report = (
        "# DEMO – synthetischer lokaler Probelauf\n\n"
        "Dieser Lauf simuliert G0, G1, G2 und G3 mit DEMO_SIMULATION. "
        "Er erteilt keine produktive Freigabe, dokumentiert keinen echten InVideo-Render, "
        "keinen Upload und keine Veröffentlichung. Native Codex-Worker wurden hier "
        "durch ausdrücklich synthetische result.json-Fixtures ersetzt.\n\n"
        f"Projekt: `{pid}`. Freeze: `{result['freeze']}`. "
        f"Nächster Zustand: `WAITING_FOR_HUMAN / {result['next']['gate']}`.\n\n"
        "| Nr. | Prüfung | Tatsächlicher Nachweis |\n| --- | --- | --- |\n"
        + checklist
        + "\n\nDie SRT ist eine zeitlich geschätzte DEMO-Untertiteldatei. "
        "Schriftbreite, eingebrannte Darstellung und Synchronität zu tatsächlicher "
        "Sprache wurden mangels Render nicht bestätigt. Alle menschlichen "
        "Handoff-Checklisten beginnen unausgefüllt.\n\n"
        + media_text
        + "\n\n## Unveränderte ursprüngliche Fassungen\n\n"
        "| Artefakt | Datei | SHA-256 der ursprünglichen Bytes |\n| --- | --- | --- |\n"
        + versions
        + "\n\nDer Snapshot enthält ausschließlich synthetische Artefakte, Quellen, "
        "Freeze-Dateien, Handoffs und DEMO-Entscheidungen. Maschinenpfade in "
        "Anleitungen und DEMO_RESULT.json sind neutralisiert; private Logs und "
        "Produktionsdaten werden nicht kopiert. Dieser Snapshot dient zum Lesen; "
        "die ausführbare Projektablage bleibt im separaten DEMO-Speicher.\n"
    )
    path = target / "REPORT.md"
    path.write_text(report, encoding="utf-8")
    return path


def run_demo(home: Path, repo: Path, with_video: bool = False) -> dict[str, Any]:
    """Exercise imports and synthetic gates, then stop before any real production."""
    from .engine import Pipeline
    from .subtitles import generate_srt, validate_srt

    pipeline = Pipeline(Path(home).expanduser() / "demo", repo)
    _configure_demo(pipeline)
    pipeline.approve_g0(DEMO_OPERATOR, _simulation_confirmation, simulation=True)
    pid = pipeline.new(DEMO_TOPIC, demo=True)
    root = pipeline.project(pid)
    prepare_sources(root)
    artifacts = fixtures(pid)
    imported_roles: list[str] = []
    original_versions: dict[str, str] = {}

    def import_role(role: str, identifiers: tuple[str, ...]) -> None:
        step = pipeline.step(pid)
        _require(step.get("status") == "READY_FOR_WORKER" and step.get("role") == role, f"Rollenfolge vor {role}: {step}")
        envelope = {"artifacts": [artifacts[identifier] for identifier in identifiers]}
        result_path = root / "workers" / "DEMO" / role / "result.json"
        write_json(result_path, envelope, exclusive=True)
        pipeline.import_batch(pid, load_json(result_path)["artifacts"])
        imported_roles.append(role)
        for identifier in identifiers:
            original_versions[identifier] = digest(root / "artifacts" / identifier / "v0.1.0.json")

    def simulate_gate(gate: str) -> None:
        step = pipeline.step(pid)
        _require(step.get("status") == "WAITING_FOR_HUMAN" and step.get("gate") == gate, f"Gatefolge vor {gate}: {step}")
        record = pipeline.approve(gate, pid, DEMO_OPERATOR, _simulation_confirmation, simulation=True)
        _require(record["kind"] == "DEMO_SIMULATION", f"{gate} wurde produktiv eingetragen.")

    import_role("GAMMA", ("A01",))
    try:
        pipeline.import_batch(pid, [artifacts["A02"]])
    except PipelineError as exc:
        blocked_without_g1 = str(exc)
        _require("G1" in blocked_without_g1, "Recherche wurde nicht wegen des fehlenden G1 blockiert.")
    else:
        raise PipelineError("DEMO-Prüfung fehlgeschlagen: Recherche vor G1 war möglich.")
    simulate_gate("G1")
    import_role("RESEARCH", ("A02",))
    import_role("ALPHA", ("A03",))
    simulate_gate("G2")
    import_role("BETA", ("A04", "A05", "A06"))
    import_role("QA_RED_TEAM", ("A07",))
    freeze = pipeline.preflight(pid)
    pipeline.verify_freeze(pid)
    simulate_gate("G3")
    current = pipeline.artifacts(pid)
    _require(all(artifact["beispiel"] for artifact in current.values()), "Nicht als DEMO markiertes Artefakt.")
    for identifier, fingerprint in original_versions.items():
        _require(digest(root / "artifacts" / identifier / "v0.1.0.json") == fingerprint, f"{identifier} Entwurf wurde überschrieben.")
    srt_path = root / "handoff" / "invideo" / "DEMO_ESTIMATED.srt"
    srt_path.write_text(generate_srt(current["A05"]["inhalt"], current["A06"]["inhalt"]), encoding="utf-8")
    subtitle_report = validate_srt(srt_path)
    _require(not any(check["status"] == "fehlgeschlagen" for check in subtitle_report["checks"]), "DEMO-SRT verletzt messbare Untertitelregeln.")

    media = None
    if with_video:
        path = _negative_video(root)
        media = pipeline.qa(pid, path, "preview")
        checks = media.get("checks", [])
        _require(any(check["id"] == "video_resolution" and check["status"] == "fehlgeschlagen" for check in checks), "Echte Auflösungsprüfung hat den Negativtest nicht abgewiesen.")
        _require(media.get("ergebnis") == "nacharbeit_erforderlich", "Negatives Video wurde als freigabefähig ausgegeben.")

    blocked_media_gates = {}
    for gate in ("G4", "G5a", "G5b"):
        try:
            pipeline.approve(gate, pid, DEMO_OPERATOR, _simulation_confirmation, simulation=True)
        except PipelineError as exc:
            blocked_media_gates[gate] = str(exc)
        else:
            raise PipelineError(f"DEMO-Prüfung fehlgeschlagen: {gate} war ohne echte Medien-/Plattformnachweise möglich.")
    state = pipeline.state(pid)
    _require(set(state["approvals"]) == {"G1", "G2", "G3"}, "Unerwartete Medien- oder Produktionsfreigabe.")
    _require(not state["reviews"] and not state["attestations"], "Eine menschliche Prüfung wurde im DEMO-Lauf fingiert.")
    _require(not any(identifier in state["current"] for identifier in ("A09", "A11", "A12")), "Ein Final, Upload oder Analytics wurde behauptet.")
    if with_video:
        preview = pipeline.artifacts(pid).get("A08")
        _require(preview is not None and preview["beispiel"] and preview["inhalt"]["render_real"] is False, "Negative Testdatei wurde als echter InVideo-Render ausgegeben.")
    else:
        _require("A08" not in state["current"], "Ein tatsächlicher Render wurde ohne Medienprüfung behauptet.")
    next_step = pipeline.step(pid)
    expected_gate = "G4" if with_video else "G3_INVIDEO"
    _require(next_step.get("status") == "WAITING_FOR_HUMAN" and next_step.get("gate") == expected_gate, "Demo hat die unbestätigte Medienproduktion überschritten.")
    result = {
        "beispiel": True,
        "typ": "DEMO_SIMULATION",
        "projekt_id": pid,
        "project_path": str(root),
        "freeze": freeze,
        "simulated_gates": ["G0", "G1", "G2", "G3"],
        "worker_roles": imported_roles,
        "blocked_without_g1": blocked_without_g1,
        "blocked_media_gates": blocked_media_gates,
        "subtitles": subtitle_report,
        "media": media,
        "next": next_step,
        "published": False,
        "production_approvals": 0,
    }
    report_path = _snapshot(pipeline, pid, result, original_versions)
    result["report_path"] = str(report_path)
    result["snapshot_path"] = str(report_path.parent)
    return result
