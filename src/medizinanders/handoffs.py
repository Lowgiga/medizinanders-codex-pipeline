"""Deterministic, self-contained files for the pipeline's human handoffs.

These builders prepare files only. They never grant a gate, attest a check, render
media, contact InVideo, upload a video, or change project state.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .errors import PipelineError
from .util import canonical, digest, write_json


DISCLAIMER = "Journalistischer Analyse-Content. Kein medizinischer Rat."
CHECK_IDS = (
    "voiceover_exact",
    "pronunciation",
    "subtitle_sync_100ms",
    "subtitle_visual",
    "font_layout",
    "burned_subtitles",
    "smartphone_listening",
    "disclaimer_visual",
    "rights",
    "ai_label",
    "patient_privacy",
    "audio_music_verified",
)

_MEDICAL = re.compile(
    r"wirkt|wirkung|wirksam|therap|diagnos|dosis|dosier|prognos|schaden|schäd|"
    r"nebenwirk|sterb|risiko|\brisk|medikament|arznei|impf|krank|krebs|"
    r"behandl|heilung|heilmittel|klinisch|patient|mortality|efficacy|"
    r"side[ -]?effect|\btreatment\b|\bharm\b",
    re.IGNORECASE,
)
_LEGAL = re.compile(
    r"steuer|\btaxes?\b|taxation|personenbezog|identifi(?:zier|able)|"
    r"identifizier|einwillig|patientendat|patientenfoto|patientenbild|"
    r"datenschutz|privatsph|werbung|werblich|sponsor|markenrecht|urheber|"
    r"rechtlich|haftung|verleumd|persönlichkeitsrecht|gesicht|"
    r"(?:echte?|real|identifiable)[ -]?(?:person|patient)",
    re.IGNORECASE,
)
_PERSON_FLAGS = {
    "identifizierbare_person",
    "identifizierbare_personen",
    "identifiable_person",
    "contains_real_person",
    "person_erkennbar",
    "patientendaten",
    "personenbezogene_daten",
    "patient_privacy_risk",
}
_CLINICAL_FIELDS = (
    "population",
    "design",
    "vergleich",
    "endpunkt",
    "absolute_wirkung",
    "relative_wirkung",
    "unsicherheit",
    "interessenkonflikte",
    "grenzen",
)

PROFILE: dict[str, Any] = {
    "id": "MA-SHORT-58-v1.0",
    "duration_ms": 58000,
    "frames": 1740,
    "video": {
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
        "sample_aspect_ratio": "1:1",
        "scan": "progressive",
        "frame_rate": "30/1",
        "frame_rate_mode": "CFR",
        "pixel_format": "yuv420p",
        "colour": "BT.709 SDR",
        "codec": "AVC/H.264",
        "profile": "High",
        "level": "4.1",
        "bitrate_target_bps": 10000000,
        "bitrate_cap_bps": 16000000,
        "closed_gop_frames": 60,
        "b_frames": 2,
        "container": "MP4",
        "faststart": True,
    },
    "audio": {
        "codec": "AAC-LC",
        "sample_rate_hz": 48000,
        "channels": 2,
        "bitrate_bps": 384000,
        "integrated_lufs_target": -14,
        "integrated_lufs_min": -15,
        "integrated_lufs_max": -13,
        "true_peak_max_dbtp": -1.5,
        "music_below_voice_db_target": 18,
        "music_below_voice_db_min": 15,
        "music_below_voice_db_max": 21,
        "remove_music_if_unmeasurable": True,
        "silent_from_ms": 54000,
    },
    "subtitles": {
        "language": "de",
        "encoding": "UTF-8",
        "format": "SRT",
        "burned_in_required": True,
        "font": "Montserrat Bold",
        "font_size_px": 52,
        "colour": "white",
        "max_lines": 2,
        "max_characters_per_line": 28,
        "max_characters_per_second": 18,
        "min_cue_duration_ms": 800,
        "max_cue_duration_ms": 4000,
        "max_sync_error_ms": 100,
        "safe_x_px": [90, 930],
        "safe_y_px": [192, 1536],
        "subtitle_bottom_px": 1520,
        "source_hint_y_px": [1200, 1320],
    },
    "disclaimer": {
        "start_ms": 54000,
        "end_ms": 58000,
        "background": "black",
        "text": DISCLAIMER,
        "other_visuals": False,
        "audio": False,
    },
}

PROFILE_MD = f"""### Verbindliches Profil MA-SHORT-58-v1.0

- Dauer exakt 58,000 Sekunden, 1.740 Frames; 1080 × 1920 Pixel, 9:16,
  SAR 1:1, progressive, 30/1 fps CFR.
- MP4 mit Faststart; AVC/H.264 High, Level 4.1; yuv420p, BT.709 SDR;
  Videoziel 10 Mbit/s, Obergrenze 16 Mbit/s; geschlossenes GOP 60 Frames,
  B-Frames 2. Encoder-Zielwerte müssen anhand echter Einstellungen belegt werden.
- AAC-LC, 48 kHz, Stereo, 384 kbit/s; integrierte Lautheit -14 LUFS
  (zulässig -15 bis -13 LUFS), True Peak maximal -1,5 dBTP.
- Musik 18 dB unter der Stimme (zulässig 15 bis 21 dB). Den relativen Pegel
  mit getrennten Spuren oder belastbarer Messung nachweisen. Ist das nicht
  messbar, Musik vollständig entfernen. Ein Ducking-Regler belegt den Pegel nicht.
- Deutsche UTF-8-SRT und fest eingebrannte Untertitel: Montserrat Bold,
  52 px, weiß; höchstens zwei Zeilen, 28 Zeichen je Zeile und 18 Zeichen/s;
  Cue-Dauer 0,8 bis 4,0 s; maximale Abweichung vom tatsächlichen Voiceover 100 ms.
- Text-Sicherheitsbereich x=90..930, y=192..1536 Pixel; Untertitel-Unterkante
  y=1520; Quellenhinweise y=1200..1320. Sichtprüfung am echten Video erforderlich.
- 54,000 bis 58,000 s: ausschließlich schwarzer Hintergrund und der Text
  „{DISCLAIMER}“. Keine weiteren Bilder, Quellenhinweise, Logos, Untertitel,
  Stimme, Musik oder sonstigen Audiosignale in diesen vier Sekunden.
"""


def _content(artifacts: dict, artifact_id: str, *, required: bool = False) -> dict:
    artifact = artifacts.get(artifact_id)
    if not isinstance(artifact, dict):
        if required:
            raise PipelineError(f"Handoff benötigt {artifact_id}.")
        return {}
    content = artifact.get("inhalt", artifact)
    if not isinstance(content, dict):
        raise PipelineError(f"Handoff: {artifact_id}.inhalt muss ein Objekt sein.")
    return content


def _items(value: Any) -> list:
    return value if isinstance(value, list) else []


def _strings(value: Any):
    """Only inspect values; words in schema field names are not review triggers."""
    if isinstance(value, str):
        if value != DISCLAIMER:
            yield value
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from _strings(value[key])
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _flagged(value: Any, flags: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            (key in flags and child is True) or _flagged(child, flags)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_flagged(child, flags) for child in value)
    return False


def _matched(value: Any, pattern: re.Pattern) -> str | None:
    for string in _strings(value):
        match = pattern.search(string)
        if match:
            return match.group(0)
    return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def _fence(value: Any, language: str = "") -> str:
    content = value if isinstance(value, str) else _json(value)
    runs = re.findall(r"`+", content)
    fence = "`" * max(3, max((len(run) + 1 for run in runs), default=3))
    return f"{fence}{language}\n{content}\n{fence}\n"


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return "" if value is None else str(value)


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(value.rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    temp.replace(path)
    return path


def _path(root: Path, value: Path) -> str:
    try:
        return value.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(value.resolve())


def _sha(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise PipelineError("Handoff benötigt einen echten SHA-256 mit 64 Hex-Zeichen.")
    return value.lower()


def _identity(artifacts: dict) -> str:
    lines = []
    for artifact_id in sorted(artifacts):
        value = artifacts[artifact_id]
        if not isinstance(value, dict):
            continue
        # Gate promotion changes version/status/date/input references, not the
        # reviewed substance. Source hashes are already inside A02.inhalt.
        content = value.get("inhalt", value)
        fingerprint = hashlib.sha256(canonical(content)).hexdigest()
        lines.append(
            f"- {artifact_id}; kanonischer Inhalts-SHA-256 `{fingerprint}`."
        )
    return "\n".join(lines) or "Keine Artefakte übergeben."


def _review_requirements(artifacts: dict) -> dict:
    a03 = _content(artifacts, "A03", required=True)
    a05 = _content(artifacts, "A05")
    a06 = _content(artifacts, "A06")
    reasons: dict[str, list[str]] = {"medical": [], "legal": []}
    ids: dict[str, list[str]] = {"medical": [], "legal": []}
    for kind in reasons:
        if a03.get(f"{kind}_review_required") is True:
            reasons[kind].append(f"A03.{kind}_review_required = true.")
    for claim in _items(a03.get("claims")):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id", "ohne ID"))
        for kind, flag, pattern in (
            ("medical", "medizinisch_relevant", _MEDICAL),
            ("legal", "rechtlich_relevant", _LEGAL),
        ):
            match = _matched(claim, pattern)
            if claim.get(flag) is True or match:
                ids[kind].append(claim_id)
                trigger = f"{flag} = true" if claim.get(flag) is True else f"Wortstamm „{match}“"
                reasons[kind].append(f"Claim {claim_id}: {trigger}.")
    for artifact_id, content in (("A03", a03), ("A05", a05)):
        for kind, pattern in (("medical", _MEDICAL), ("legal", _LEGAL)):
            match = _matched(content, pattern)
            if match:
                reasons[kind].append(f"{artifact_id}: Formulierung oder Risiko mit Wortstamm „{match}“.")
    scenes = _items(a06.get("szenen"))
    for kind, pattern in (("medical", _MEDICAL), ("legal", _LEGAL)):
        match = _matched(scenes, pattern)
        if match:
            reasons[kind].append(f"A06: Szenenformulierung mit Wortstamm „{match}“.")
    if _flagged(a03, {"medizinisch_relevant", "medical_review_required"}):
        reasons["medical"].append("Explizites medizinisches Review-Flag in A03.")
    if _flagged(a03, {"rechtlich_relevant", "legal_review_required"}):
        reasons["legal"].append("Explizites rechtliches Review-Flag in A03.")
    if _flagged({"a03": a03, "a05": a05, "a06": a06}, _PERSON_FLAGS):
        reasons["legal"].append("Identifizierbare Person oder personenbezogenes Risiko markiert.")
    for asset in _items(a06.get("assets")):
        if not isinstance(asset, dict):
            reasons["legal"].append("Unvollständiger Asset-Eintrag; Rechte nicht nachgewiesen.")
            continue
        asset_id = str(asset.get("id", "ohne ID"))
        if asset.get("recht_status") != "geklaert" or not asset.get("nachweis"):
            reasons["legal"].append(f"Asset {asset_id}: Rechte offen oder Nachweis fehlt.")
        if asset.get("imitierte_stimme") is True:
            reasons["legal"].append(f"Asset {asset_id}: imitierte Stimme; Zustimmung und Nutzungsrechte prüfen.")
        subject = {key: asset.get(key) for key in ("typ", "herkunft", "risiken", "personen")}
        match = _matched(subject, _LEGAL)
        if match:
            reasons["legal"].append(f"Asset {asset_id}: Personen-/Rechtsrisiko „{match}“.")
    for kind in reasons:
        reasons[kind] = list(dict.fromkeys(reasons[kind]))
        ids[kind] = sorted(set(ids[kind]))
    return {"reasons": reasons, "claim_ids": ids}


def _sources_md(a02: dict) -> str:
    chunks = []
    for source in _items(a02.get("sources")):
        if not isinstance(source, dict):
            chunks.append("Unvollständiger Quellen-Eintrag: " + _fence(source, "json"))
            continue
        chunks.append(f"### Quelle {source.get('id', 'ohne ID')}\n")
        details = {key: source.get(key) for key in (
            "id", "url", "titel", "typ", "zugriff", "fundstelle", "abgerufen_am",
            "sha256", "original_geoeffnet", "lokaler_pfad",
        )}
        chunks.append(_fence(details, "json"))
        chunks.append("Klinische Parameter; null bedeutet nicht angegeben, nicht nachgewiesen:\n")
        params = source.get("klinische_parameter")
        params = params if isinstance(params, dict) else {}
        chunks.append(_fence({field: params.get(field) for field in _CLINICAL_FIELDS}, "json"))
    if not chunks:
        chunks.append("Keine Quellen übergeben. Eine fachliche Evidenzprüfung ist damit nicht belegt.\n")
    chunks.append("### Suchprotokoll, Gegenbelege und Korrekturen\n")
    chunks.append(_fence({key: a02.get(key, []) for key in (
        "suchprotokoll", "gegenbelege", "korrekturen_retraktionen",
    )}, "json"))
    return "\n".join(chunks)


def _claims_md(a03: dict) -> str:
    chunks = []
    for claim in _items(a03.get("claims")):
        chunks.append(f"### Claim {claim.get('id', 'ohne ID') if isinstance(claim, dict) else 'ohne ID'}\n")
        chunks.append(_fence(claim, "json"))
    if not chunks:
        chunks.append("Keine Claims übergeben; dies ersetzt keine Prüfung faktischer Aussagen.\n")
    chunks.append("### Faktenmatrix und Risikoübersicht\n")
    chunks.append(_fence({key: a03.get(key, []) for key in (
        "faktenmatrix", "risikoübersicht", "risikouebersicht", "psychologie_map",
    )}, "json"))
    return "\n".join(chunks)


def _planned_md(a05: dict) -> str:
    if not a05:
        return (
            "A05 liegt noch nicht vor. Dieses Paket umfasst noch keine konkrete "
            "Skriptfassung. Nach Vorliegen oder Änderung von A05 Paket neu erzeugen "
            "und die neuen Formulierungen fachlich prüfen lassen.\n"
        )
    return (
        "Die folgende geplante Fassung ist vollständig eingebettet. Fachliche "
        "Freigabe umfasst Wortlaut, Claims, Einschränkungen, Titel, Thumbnail, "
        "Beschreibung, CTA, Overlays, Quellen und Disclaimer. Änderungen erfordern "
        "ein neues Paket und eine Entscheidung mit dessen Hash.\n\n"
        + _fence(a05, "json")
    )


def build_review_packets(project_path: Path, artifacts: dict) -> dict:
    """Prepare medical/legal packets and conservative, hash-bound examples.

    Both packets are written even when the corresponding review is not triggered.
    Actual ``medical.decision.json``/``legal.decision.json`` files are never touched.
    """
    root = Path(project_path)
    directory = root / "review"
    a02 = _content(artifacts, "A02")
    a03 = _content(artifacts, "A03", required=True)
    a05 = _content(artifacts, "A05")
    a06 = _content(artifacts, "A06")
    requirements = _review_requirements(artifacts)
    review_claim_ids = sorted({
        str(claim["id"]) for claim in _items(a03.get("claims"))
        if isinstance(claim, dict) and claim.get("id") and claim.get("einsatz") != "nein"
    })
    result: dict[str, Any] = {"paths": []}
    # Later artefacts and gate decisions must not invalidate a content review.
    inputs = {key: artifacts[key] for key in ("A01", "A02", "A03", "A04", "A05", "A06") if key in artifacts}
    for kind, title in (("medical", "Medizinisches Review"), ("legal", "Rechtliches Review")):
        required = bool(requirements["reasons"][kind])
        reasons = requirements["reasons"][kind]
        qualification = (
            "Medizinisch qualifizierte Person mit dokumentierter, für die Claims "
            "geeigneter Fachkompetenz; Qualifikation und Identität selbst angeben."
            if kind == "medical" else
            "Rechtlich qualifizierte Person mit dokumentierter, für die fraglichen "
            "Rechte, Steuern und Persönlichkeitsrechte geeigneter Fachkompetenz."
        )
        packet = (
            f"# {title}: Prüfpaket\n\n"
            f"Review erforderlich: {'JA' if required else 'NEIN – kein automatischer Trigger erkannt'}.\n\n"
            "Dieses Paket und sein Hash sind keine Freigabe. Suchtreffer, ein "
            "Quellenlink und ein als geklärt markierter Rechte-Eintrag ersetzen "
            "keine Prüfung des Originals oder des tatsächlichen Nachweises.\n\n"
            "## Auslöser\n\n"
            + ("\n".join(f"- {reason}" for reason in reasons) if reasons else "Keine erkannten Auslöser.")
            + "\n\n## Eingefrorener Inhalt dieses Prüfpakets\n\n"
            + _identity(inputs)
            + "\n\n## Auftrag an die prüfende Person\n\n"
            + qualification
            + "\n\nAlle Originalquellen und Fundstellen öffnen. Population, Design, "
            "Vergleich, Endpunkt, absolute und relative Wirkung, Unsicherheit, "
            "Interessenkonflikte und Grenzen gegen den Originaltext prüfen. "
            "Kausalität, Übertragbarkeit und Aussagegrenzen ausdrücklich bewerten. "
            "UNBEWIESEN, WIDERLEGT oder einsatz=nein bedeutet keine Freigabe als "
            "Fakt. Einschränkungen müssen im geplanten Wortlaut und in Metadaten "
            "erhalten bleiben.\n\n"
            "Rechte, Marken, Werbung/Steuern, identifizierbare Personen, "
            "Patientendaten, Einwilligungen, KI-Illustrationen und imitierte "
            "Stimmen anhand echter Dokumente prüfen. Offene Rechte verhindern "
            "die Produktion beziehungsweise Veröffentlichung.\n\n"
            "## Claims und Einschränkungen\n\n"
            + _claims_md(a03)
            + "\n## Quellen und klinische Parameter\n\n"
            + _sources_md(a02)
            + "\n## Geplante Formulierungen einschließlich Metadaten\n\n"
            + _planned_md(a05)
            + "\n## Geplante Szenen und sämtliche Assets\n\n"
            + _fence({"szenen": a06.get("szenen", []), "assets": a06.get("assets", [])}, "json")
            + "\n## Menschliche Entscheidung\n\n"
            f"`{kind}.decision.example.json` ist ausschließlich eine Vorlage. "
            f"Eine ausgefüllte Entscheidung heißt `{kind}.decision.json`. "
            "Erlaubte Entscheidungen: approved, rejected, changes_required. "
            "reviewer und qualification müssen wahrheitsgemäß ausgefüllt sein. "
            "claim_ids muss sämtliche verwendbaren Claims (einsatz != nein) "
            "umfassen; die Vorlage enthält deren IDs, ohne eine Prüfung zu "
            "behaupten. notes dokumentiert "
            "Befund, Grenzen und nötige Änderungen. reviewed_packet_sha256 muss "
            "der SHA-256 der unveränderten UTF-8-Datei dieses Pakets sein. "
            "Nach Paketänderung ist eine alte Entscheidung ungültig. "
            "Eine genehmigte Entscheidung erteilt selbst keine Pipeline-Gatefreigabe.\n"
        )
        packet_path = _write(directory / f"{kind.upper()}_REVIEW_PACKET.md", packet)
        packet_sha = digest(packet_path)
        sha_path = _write(directory / f"{kind.upper()}_REVIEW_PACKET.sha256", packet_sha)
        example_path = directory / f"{kind}.decision.example.json"
        write_json(example_path, {
            "decision": "changes_required",
            "reviewer": "",
            "qualification": "",
            "claim_ids": review_claim_ids,
            "notes": "Ungeprüfte Vorlage. Entscheidung, Person, Qualifikation und Befund selbst eintragen.",
            "reviewed_packet_sha256": packet_sha,
        })
        result[f"{kind}_required"] = required
        result[f"{kind}_packet"] = packet_path
        result[f"{kind}_packet_sha256"] = packet_sha
        result[f"{kind}_decision_example"] = example_path
        result[f"{kind}_claim_ids"] = requirements["claim_ids"][kind]
        result[f"{kind}_reasons"] = reasons
        result["paths"].extend((packet_path, sha_path, example_path))
    return result


def _checklist(kind: str, *, freeze_id: str | None = None, final_sha: str | None = None) -> dict:
    checklist = {
        "checklist": kind,
        "example": True,
        "operator": "",
        "checked_at": None,
        "freeze_id": freeze_id or None,
        "preview_sha256": None,
        "final_sha256": final_sha,
        "checks": {check_id: False for check_id in CHECK_IDS},
        "technical_unknowns": {},
        "evidence": {},
        "notes": "Ungeprüfte Vorlage. Nur persönlich geprüfte Punkte auf true setzen und Nachweise angeben.",
    }
    if kind == "preview":
        checklist["render_invideo"] = False
    elif kind == "final":
        checklist.update({
            "musik_entfernt": False,
            "getrennte_spuren": False,
            "ducking_db": None,
        })
    return checklist


def _scenes_md(a06: dict) -> str:
    chunks = []
    for scene in _items(a06.get("szenen")):
        if not isinstance(scene, dict):
            chunks.append(_fence(scene, "json"))
            continue
        chunks.append(
            f"### Szene {scene.get('id', 'ohne ID')}: "
            f"{scene.get('start_ms', '?')}–{scene.get('ende_ms', '?')} ms\n"
        )
        # Preserve all fields, including optional operator-relevant extensions.
        chunks.append(_fence(scene, "json"))
    return "\n".join(chunks) or "Keine Szenen übergeben. Vor Rendern vollständigen Szenenplan herstellen.\n"


def _metadata(a05: dict) -> dict:
    return {key: a05.get(key) for key in (
        "titel", "thumbnail", "beschreibung", "quellenangaben", "cta", "disclaimer",
    )}


def _render_header(freeze_id: str) -> str:
    freeze = freeze_id if freeze_id else "noch kein Freeze übergeben"
    return (
        "Status: PREPARED_BEFORE_G3 – Handoff vorbereitet. NUR nach G3 rendern.\n"
        f"Freeze-Kennung: {freeze}\n\n"
        "Diese Dateien erteilen keine Freigabe. Der Operator muss die konkrete "
        "menschliche G3-Freigabe und den aktuellen unveränderten Freeze im "
        "Projekt prüfen. Eine hier genannte Freeze-Kennung allein genügt nicht. "
        "Bei Änderungen an Wortlaut, Szenen, Timing, Metadaten oder Rechten "
        "stoppen und über die Pipeline erneut prüfen/freigeben.\n"
    )


def _rights_md(a06: dict) -> str:
    return (
        "- [ ] Für jedes Bild, Video, jede Schrift, Stimme, Musik und jeden Effekt "
        "liegen Herkunft, Lizenz, erlaubte Bearbeitung und Plattform-/Werbenutzung vor.\n"
        "- [ ] Für identifizierbare Personen und Patientendaten sind Einwilligung, "
        "Datenschutz und Persönlichkeitsrechte dokumentiert.\n"
        "- [ ] KI-Illustrationen und imitierte Stimmen sind kenntlich und rechtlich geprüft.\n"
        "- [ ] Keine ungeklärten Assets werden verwendet; Stock-/InVideo-Abonnement "
        "allein ist kein Nachweis konkreter Verwendungsrechte.\n"
        "- [ ] Attribution und sonstige Lizenzauflagen sind im tatsächlichen Export erfüllt.\n\n"
        "Die folgenden Einträge sind Planangaben, keine unabhängige Bestätigung:\n\n"
        + _fence(a06.get("assets", []), "json")
    )


def build_invideo(project_path: Path, artifacts: dict, freeze_id: str, *, output_path: Path | None = None) -> list[Path]:
    """Prepare a manual InVideo bundle directly from A04/A05/A06.

    A06.invideo_prompt is deliberately not trusted or included. No video is
    rendered and no capabilities or export measurements are asserted.
    """
    root = Path(project_path)
    directory = root / "handoff" / "invideo"
    target_directory = Path(output_path) if output_path is not None else directory
    a04 = _content(artifacts, "A04", required=True)
    a05 = _content(artifacts, "A05", required=True)
    a06 = _content(artifacts, "A06", required=True)
    header = _render_header(freeze_id)
    scenes = _scenes_md(a06)
    voiceover = str(a05.get("sprechertext", ""))
    subtitles = str(a05.get("untertitel_basis", ""))
    prompt = (
        "# Vollständiger manueller InVideo-Produktionsprompt\n\n"
        + header
        + "\nErzeuge einen deutschen vertikalen Analyse-Short nach dem folgenden "
        "vollständigen Plan. Den Sprechertext wortgetreu verwenden: keine "
        "Paraphrasen, zusätzlichen Fakten, Werbeslogans oder automatischen "
        "CTAs. Nur ausdrücklich als Overlay/Quellenhinweis genannte Inhalte "
        "einblenden. Claim-IDs und technische Metadaten dienen der Kontrolle, "
        "sie werden nicht als zusätzliche Bildschirmtexte dargestellt. "
        "Provenienz und Rechte von Assets erhalten; kein Ersatz durch ungeklärtes Material.\n\n"
        + PROFILE_MD
        + "\n## Vollständige Dramaturgie und Abschnittszeiten\n\n"
        + _fence(a04, "json")
        + "\n## Exakter Sprechertext\n\n"
        + _fence(voiceover)
        + "\n## Exakte Untertitelbasis\n\n"
        + _fence(subtitles)
        + "\n## Satzfolge, Aussprache und vollständige Overlays\n\n"
        + _fence({key: a05.get(key) for key in ("wortzahl", "saetze", "aussprache", "overlays")}, "json")
        + "\n## Titel, Thumbnail, Beschreibung, Quellen, CTA und Disclaimer\n\n"
        + _fence(_metadata(a05), "json")
        + "\n## Vollständiger Szenenplan\n\n"
        + scenes
        + "\n## Vollständiges Asset- und Rechtemanifest\n\n"
        + _fence(a06.get("assets", []), "json")
        + "\n## Untertitel, Audio und Operator-Kontrolle\n\n"
        "SRT-Zeiten am tatsächlich gesprochenen Text ausrichten; eine geschätzte "
        "SRT ist kein Synchronitätsnachweis. Voiceover exakt, Aussprache einzeln "
        "abhören, Untertitel visuell und an Cue-Grenzen prüfen. Musik-/Sprachpegel "
        "belegen oder Musik entfernen. InVideo-Exportfähigkeiten sind nicht "
        "bestätigt; bei fehlenden Einstellungen nachbearbeiten und die echte "
        "Datei messen. Noch unbekannte Werte bleiben nicht_geprueft.\n"
    )
    scene_plan = (
        "# Vollständiger Szenenplan\n\n" + header + "\n" + PROFILE_MD
        + "\n## Dramaturgie\n\n" + _fence(a04, "json")
        + "\n## Szenen mit Text, Motiven, Timing, Synchronankern und Quellen\n\n" + scenes
        + "\n## Übergreifende Overlays und Aussprache\n\n"
        + _fence({key: a05.get(key) for key in ("overlays", "aussprache", "disclaimer")}, "json")
    )
    rights = "# Rechtecheck vor Produktion und Veröffentlichung\n\n" + header + "\n" + _rights_md(a06)
    expected = (
        "# Erwartete tatsächliche Produktionsdateien\n\n" + header + "\n" + PROFILE_MD
        + "\n## Übergabe\n\n"
        "1. Echten, vollständig gesichteten InVideo-Preview als "
        "`08_produktion/inbox/preview.mp4` ablegen; keine Dummy-Datei.\n"
        "2. Nach Nachbearbeitung echten Final als "
        "`08_produktion/inbox/final.mp4` ablegen.\n"
        "3. Deutsche UTF-8-SRT des tatsächlichen Finals als "
        "`08_produktion/inbox/subtitles.srt` ablegen; zusätzlich eingebrannte Untertitel.\n"
        "4. Exportprotokoll, Rechnung/Lizenzbelege, getrennte Tonspuren (wenn "
        "benötigt), Messberichte und echte Encoder-Einstellungen aufbewahren.\n\n"
        "Die Vorgaben sind Ziele des Produktionsprofils. Dieser Handoff hat "
        "keinen Export erzeugt oder geprüft. InVideo kann je nach Tarif und "
        "aktueller Oberfläche einzelne Werte nicht einstellen/exportieren. "
        "Solche Punkte nachbearbeiten und messen oder mit echten Dokumenten "
        "belegen; nicht als automatisch bestanden markieren. Ist der "
        "Musikabstand nicht nachweisbar, Musik entfernen.\n\n"
        "Die Checklist-Vorlagen enthalten ausschließlich false. Für den "
        "tatsächlich betrachteten Preview/Final dessen SHA-256 eintragen und "
        "jeden menschlich geprüften Punkt einzeln bestätigen. technische "
        "Unbekannte dürfen unter technical_unknowns als "
        '`{"check_id": {"nachweis": "projekt/echtes-dokument.pdf", "sha256": "Hash der Datei"}}` '
        "nur mit realen, passenden Nachweisen dokumentiert werden. Ein solcher "
        "Nachweis ersetzt keine messbare Videoeigenschaft und keine Hör-/Sichtprüfung.\n"
    )
    steps = (
        "# Manueller Operator-Ablauf für InVideo\n\n" + header
        + "\n1. Die persönliche G3-Freigabe und den unveränderten aktuellen Freeze "
        "prüfen. Ohne G3 nicht in InVideo rendern und keine kostenpflichtige "
        "Produktionsaktion starten.\n"
        "2. Im eigenen InVideo-Konto aktuelle Verfügbarkeit, Tarif, Credits, "
        "Gebühren, Wasserzeichen, erlaubte kommerzielle Nutzung und "
        "Exportmöglichkeiten prüfen. Dieses Projekt hat kein Konto geöffnet, "
        "keine API aufgerufen und keinen Tarif oder Export garantiert.\n"
        "3. Den vollständigen INVIDEO_PROMPT.txt in den manuellen Workflow "
        "übernehmen. Sprechertext, Satzfolge, Motive und Zeitfenster kontrollieren; "
        "automatische Umschreibungen und weitere CTAs verhindern.\n"
        "4. Konkrete Stock-/KI-Assets, Font und Stimme mit den echten Rechtebelegen "
        "abgleichen. Keine identifizierbaren Personen/Patienten oder imitierte "
        "Stimmen ohne dokumentierte nötige Rechte verwenden.\n"
        "5. Aussprache korrigieren. Untertitel am echten Voiceover timen und "
        "gemäß eingebettetem Profil gestalten. 54..58 s bleiben schwarze "
        "Disclaimer-Tafel ohne jeden Ton.\n"
        "6. Soweit verfügbar getrennte Sprach- und Musikspuren exportieren. "
        "Musikabstand messen; bei unmessbarem Abstand Musik entfernen. Keine "
        "erfundene Aussage über Tool-Funktionen, Pegel oder Exportparameter.\n"
        "7. Den echten Preview in 08_produktion/inbox/preview.mp4 "
        "übergeben und vollständig abhören/ansehen, einschließlich Smartphone. "
        "PREVIEW_CHECKLIST.example.json als eigene PREVIEW_CHECKLIST.json "
        "ausfüllen, Operator und Datei-Hash angeben. Nur tatsächlich geprüfte "
        "Punkte bestätigen; render_invideo ausschließlich nach echtem "
        "InVideo-Render auf true setzen. Gate-Freigabe anschließend in der Pipeline erteilen.\n"
        "8. Nachbearbeitung und vollständigen Final prüfen. Final und UTF-8-SRT "
        "in die vorgesehenen Inbox-Dateien legen. FINAL_CHECKLIST.example.json "
        "als FINAL_CHECKLIST.json anhand des tatsächlichen Final-Hash ausfüllen. "
        "musik_entfernt nur bei tatsächlich entfernter Musik auf true setzen. "
        "Bei Musik getrennte_spuren ausschließlich mit echten getrennten "
        "Spuren bestätigen und ducking_db als gemessenen relativen Musikpegel "
        "(-21 bis -15 dB, Ziel -18 dB) eintragen. Ohne diesen Nachweis Musik entfernen. "
        "Berichte und echte Dokumente für nicht direkt messbare Encoder-Zielwerte "
        "beifügen. Änderungen erfordern den vorgesehenen Rückweg und neue Freigaben.\n\n"
        + PROFILE_MD
    )
    manifest = {
        "status": "PREPARED_BEFORE_G3",
        "render_requires": "Persönliche G3-Freigabe und unveränderter gültiger Freeze",
        "freeze_id": freeze_id or None,
        "profile": PROFILE,
        "assets": a06.get("assets", []),
        "scenes": a06.get("szenen", []),
        "rights_verified_by_builder": False,
        "invideo_capabilities_verified_by_builder": False,
        "generated_media": False,
    }
    files = {
        "INVIDEO_PROMPT.txt": prompt,
        "SCENE_PLAN.md": scene_plan,
        "VOICEOVER.txt": voiceover,
        "SUBTITLE_BASE.txt": subtitles,
        "ASSET_MANIFEST.yaml": yaml.safe_dump(manifest, allow_unicode=True, sort_keys=True),
        "RIGHTS_CHECKLIST.md": rights,
        "EXPECTED_OUTPUT.md": expected,
        "OPERATOR_STEPS.md": steps,
    }
    paths = [_write(target_directory / name, content) for name, content in files.items()]
    for kind in ("PREVIEW", "FINAL"):
        path = target_directory / f"{kind}_CHECKLIST.example.json"
        write_json(path, _checklist(kind.lower(), freeze_id=freeze_id))
        paths.append(path)
    return paths


def _public_sources(artifacts: dict) -> tuple[list[str], list[str]]:
    a02 = _content(artifacts, "A02")
    a03 = _content(artifacts, "A03")
    a05 = _content(artifacts, "A05")
    claims = {item.get("id"): item for item in _items(a03.get("claims")) if isinstance(item, dict)}
    used_ids = set(a05.get("quellen", [])) if isinstance(a05.get("quellen"), list) else set()
    for sentence in _items(a05.get("saetze")):
        if isinstance(sentence, dict):
            for claim_id in _items(sentence.get("claim_ids")):
                used_ids.update(_items(claims.get(claim_id, {}).get("source_ids")))
    for citation in _items(a05.get("quellenangaben")):
        if isinstance(citation, dict):
            source_id = citation.get("source_id", citation.get("id"))
            if source_id:
                used_ids.add(source_id)
        elif isinstance(citation, str):
            used_ids.add(citation)
    sources = [source for source in _items(a02.get("sources")) if isinstance(source, dict)]
    known_ids = {source.get("id") for source in sources}
    # Plain bibliographic citation text is preserved separately in the handoff.
    filter_ids = used_ids & known_ids
    public = []
    blocked = []
    for source in sources:
        if filter_ids and source.get("id") not in filter_ids:
            continue
        if source.get("zugriff") == "geprueft" and source.get("original_geoeffnet") is True and source.get("url"):
            public.append(f"{source.get('titel', source.get('id', 'Quelle'))}: {source['url']}")
        else:
            blocked.append(str(source.get("id", "ohne ID")))
    return public, blocked


def build_youtube(
    project_path: Path,
    artifacts: dict,
    final_path: Path,
    final_sha: str,
    srt_path: Path,
    *, output_path: Path | None = None,
) -> list[Path]:
    """Prepare metadata and manual decisions bound to an existing final file."""
    root = Path(project_path)
    directory = root / "handoff" / "youtube"
    target_directory = Path(output_path) if output_path is not None else directory
    a05 = _content(artifacts, "A05", required=True)
    final = Path(final_path)
    srt = Path(srt_path)
    if not final.is_file() or not srt.is_file():
        raise PipelineError("YouTube-Handoff benötigt eine echte Finaldatei und eine vorhandene SRT.")
    final_sha = _sha(final_sha)
    if digest(final) != final_sha:
        raise PipelineError("Finaldatei wurde geändert: SHA-256 passt nicht zum YouTube-Handoff.")
    try:
        srt_bytes = srt.read_bytes()
        srt_bytes.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise PipelineError("YouTube-Handoff benötigt eine lesbare UTF-8-SRT.") from exc
    if not srt_bytes.strip():
        raise PipelineError("YouTube-Handoff benötigt eine nichtleere SRT.")
    srt_sha = hashlib.sha256(srt_bytes).hexdigest()
    public_sources, blocked_sources = _public_sources(artifacts)
    hashtags = a05.get("hashtags", ["#MedizinAnders", "#Gesundheitswissen", "#Shorts"])
    if not isinstance(hashtags, list) or any(not isinstance(tag, str) for tag in hashtags):
        raise PipelineError("YouTube-Hashtags müssen eine Liste von Texten sein.")
    tags_line = " ".join(tag if tag.startswith("#") else "#" + tag for tag in hashtags)
    description_parts = [_text(a05.get("beschreibung"))]
    disclaimer = str(a05.get("disclaimer", ""))
    if disclaimer and disclaimer not in description_parts[0]:
        description_parts.append(disclaimer)
    if public_sources:
        description_parts.append("Quellen:\n" + "\n".join(public_sources))
    if tags_line:
        description_parts.append(tags_line)
    description = "\n\n".join(part for part in description_parts if part)
    handoff = (
        "# YouTube: manuelle Upload- und Veröffentlichungsübergabe\n\n"
        "Status: vorbereitet. Dieser Handoff hat nichts hochgeladen und nichts veröffentlicht.\n\n"
        f"Finaldatei: `{_path(root, final)}`\n\nFinal-SHA-256: `{final_sha}`\n\n"
        f"Original-SRT: `{_path(root, srt)}`\n\nSRT-SHA-256: `{srt_sha}`\n\n"
        "Nur diese konkrete Finaldatei nach den erforderlichen persönlichen "
        "Freigaben manuell hochladen. Vor Upload Hash erneut vergleichen; eine "
        "neue Datei benötigt neue Prüfung. Upload zunächst privat, Verarbeitung "
        "abwarten und tatsächliches YouTube-Playback prüfen. Öffentlich schalten "
        "darf ausschließlich die verantwortliche Person nach den erforderlichen "
        "Freigaben und echten Entscheidungen; es gibt keinen automatischen Publish.\n\n"
        "## Vollständiger Titel\n\n" + _fence(_text(a05.get("titel")))
        + "\n## Vollständige Beschreibung einschließlich Quellen und Hashtags\n\n"
        + _fence(description)
        + "\n## Vollständiger Thumbnail-Plan\n\n" + _fence(a05.get("thumbnail"), "json")
        + "\n## Eingebettete ursprüngliche Quellenangaben und Metadaten\n\n"
        + _fence(_metadata(a05), "json")
        + "\n## Entscheidungen, die eine Person selbst treffen muss\n\n"
        "- KI-Kennzeichnung: tatsächlichen Inhalt und aktuelle YouTube-Regeln prüfen; "
        "ki_kennzeichnung beginnt als null.\n"
        "- Zielgruppe/Kinderausrichtung: tatsächliches Publikum selbst bestimmen; "
        "zielgruppe beginnt als null.\n"
        "- Werbung/bezahlte Kooperation: reale Finanzierung und Plattformvorgaben "
        "prüfen; werbung beginnt als null.\n"
        "- Rechte, Patientenschutz, Font, Musik, Untertitel, Smartphone-Audio und "
        "Disclaimer am tatsächlichen Final/Playback prüfen.\n\n"
        "YOUTUBE_DECISIONS.example.json ist eine unausgefüllte Vorlage, kein "
        "Veröffentlichungsnachweis. In einer eigenen YOUTUBE_DECISIONS.json echte "
        "Entscheidungen, Operator, Video-ID, URL und Sichtbarkeit eintragen. "
        "veroeffentlicht_am bleibt null, solange keine Person tatsächlich veröffentlicht hat.\n"
    )
    if blocked_sources or not public_sources:
        handoff += (
            "\n## Quellenklärung vor Upload\n\n"
            f"Nicht originalgeprüfte/fehlende öffentliche Quellen: {_json(blocked_sources)}. "
            "Vor Upload klären; fehlende Quellenprüfung wird durch diesen Handoff "
            "nicht bestätigt. Fehlende URLs werden nicht erfunden.\n"
        )
    files = {
        "YOUTUBE_HANDOFF.md": handoff,
        "TITLE.txt": _text(a05.get("titel")),
        "DESCRIPTION.txt": description,
        "TAGS.txt": tags_line,
        "THUMBNAIL_BRIEF.md": "# Vollständiger Thumbnail-Plan\n\n" + _fence(a05.get("thumbnail"), "json"),
        "SOURCE_LINKS.md": "# Quellen des Upload-Handoffs\n\n" + _sources_md(_content(artifacts, "A02")),
    }
    paths = [_write(target_directory / name, content) for name, content in files.items()]
    decisions_path = target_directory / "YOUTUBE_DECISIONS.example.json"
    write_json(decisions_path, {
        "example": True,
        "operator": "",
        "final_sha256": final_sha,
        "srt_sha256": srt_sha,
        "youtube_id": None,
        "url": None,
        "visibility": "vorbereitet",
        "ki_kennzeichnung": None,
        "zielgruppe": None,
        "werbung": None,
        "playback_pruefung": None,
        "veroeffentlicht_am": None,
        "notes": "Menschliche Entscheidungen und tatsächliche Veröffentlichung selbst dokumentieren.",
    })
    manifest_path = target_directory / "UPLOAD_MANIFEST.json"
    write_json(manifest_path, {
        "final": {"path": _path(root, final), "sha256": final_sha},
        "srt": {"path": _path(root, srt), "sha256": srt_sha},
        "uploaded_by_builder": False,
        "published_by_builder": False,
        "blocked_source_ids": blocked_sources,
    })
    copied_srt = target_directory / "subtitles.srt"
    copied_srt.write_bytes(srt_bytes)
    paths.extend((decisions_path, manifest_path, copied_srt))
    return paths


def build_playback(project_path: Path, youtube_record: dict, final_sha: str) -> Path:
    """Prepare an unconfirmed checklist for the actual YouTube playback."""
    directory = Path(project_path) / "handoff" / "playback"
    if not isinstance(youtube_record, dict):
        raise PipelineError("Playback-Handoff benötigt einen YouTube-Datensatz.")
    record = youtube_record.get("inhalt", youtube_record)
    if not isinstance(record, dict):
        raise PipelineError("Playback-Handoff benötigt einen YouTube-Inhalt als Objekt.")
    final_sha = _sha(final_sha)
    if record.get("final_sha256") not in (None, final_sha):
        raise PipelineError("YouTube-Datensatz gehört zu einer anderen Finaldatei.")
    checklist = _checklist("playback", final_sha=final_sha)
    checklist["youtube_id"] = record.get("youtube_id")
    checklist["url"] = record.get("url")
    checklist["visibility"] = record.get("visibility", "vorbereitet")
    checklist["checks"].update({
        "playback_complete": False,
        "youtube_processing_complete": False,
        "metadata_exact": False,
        "audience_decided": False,
        "advertising_decided": False,
    })
    path = directory / "PLAYBACK_CHECKLIST.example.json"
    write_json(path, checklist)
    _write(directory / "PLAYBACK_STEPS.md", (
        "# Menschliche Prüfung des tatsächlichen YouTube-Playbacks\n\n"
        f"Final-SHA-256 des Uploads: `{final_sha}`\n\n"
        f"YouTube-ID: {_text(record.get('youtube_id')) or 'noch nicht angegeben'}\n\n"
        f"URL: {_text(record.get('url')) or 'noch nicht angegeben'}\n\n"
        "Diese Anleitung und die Vorlage bestätigen keine Wiedergabe. Bei "
        "fehlender ID/URL zuerst den echten manuellen Upload dokumentieren. "
        "Das vollständig verarbeitete Video auf YouTube mit berechtigtem Konto "
        "öffnen und von Anfang bis Ende auf Desktop und Smartphone abspielen. "
        "Wortlaut und Aussprache, Lautstärke/Musik, sämtliche eingebrannten "
        "Untertitel und hochgeladene SRT, Layout, Quellen, KI-Kennzeichnung, "
        "Patientenschutz, Rechte und die stumme schwarze Disclaimer-Tafel "
        "54..58 s am Stream prüfen. YouTube kann das lokale MP4 transkodieren; "
        "ein lokaler Messbericht belegt daher kein tatsächliches Plattform-Playback.\n\n"
        "Titel, Thumbnail, Beschreibung/Quellen, Zielgruppe und Werbeangabe "
        "mit den konkreten menschlichen Upload-Entscheidungen vergleichen. "
        "PLAYBACK_CHECKLIST.example.json als eigene PLAYBACK_CHECKLIST.json "
        "ausfüllen; Operator, Zeitpunkt, ID/URL, Final-Hash und Nachweise "
        "angeben. Nur tatsächlich geprüfte Punkte auf true setzen. Fehler "
        "dokumentieren und über die Pipeline beheben; Änderungen an der "
        "Finaldatei benötigen neue Freigaben. Veröffentlichung und "
        "Sichtbarkeitswechsel erfolgen ausschließlich durch die verantwortliche Person.\n\n"
        + PROFILE_MD
    ))
    return path
