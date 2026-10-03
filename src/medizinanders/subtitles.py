"""Plain UTF-8 SRT preparation and truthful subtitle QA.

``generate_srt`` ALWAYS creates estimated editorial timing. It has no audio
input and cannot measure synchronization. Saving a generated SRT must retain
that fact in the surrounding A09/artifact metadata or operator instructions.
The SRT itself contains only captions; no fake synchronization label is burned
into the spoken text.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any


FONT_SIZE_PX = 52
MAX_PIXEL_WIDTH = 840
MAX_LINE_CHARACTERS = 28
MAX_LINES = 2
MAX_CPS = 18
MIN_CUE_MS = 800
MAX_CUE_MS = 4000
CAPTION_END_MS = 54000
GENERATED_TIMING_BASIS = "GESCHÄTZTE TIMINGS aus Text und A06-Szenen; keine Audio-Synchronmessung."

_TIME_RE = re.compile(r"^(\d{2}):([0-5]\d):([0-5]\d),(\d{3}) --> (\d{2}):([0-5]\d):([0-5]\d),(\d{3})$")
_NEGATIONS = {"nicht", "kein", "keine", "keinen", "keinem", "keiner", "keines", "nie", "niemals", "ohne", "weder"}
_UNITS = {"mg", "g", "kg", "µg", "μg", "mcg", "ng", "ml", "l", "dl", "mmol", "mmol/l", "mol/l",
          "mg/dl", "mg/l", "µg/l", "μg/l", "mmhg", "bpm", "ie", "iu", "cm", "mm", "m", "km",
          "kcal", "kj", "h", "min", "s", "sekunde", "sekunden", "minute", "minuten", "stunde", "stunden",
          "tag", "tage", "tagen", "woche", "wochen", "monat", "monate", "monaten", "jahr", "jahre", "jahren",
          "prozent", "%", "‰", "°c", "°f", "patient", "patienten", "patientin", "patientinnen", "menschen"}
_NUMBER_RE = re.compile(r"^[+\-−]?\d+(?:[.,]\d+)*(?:[–\-−]\d+(?:[.,]\d+)*)?(?:%|‰)?$")


def _check(check_id: str, status: str, actual: Any, required: str, reason: str = "") -> dict[str, Any]:
    return {"id": check_id, "status": status, "ist": actual, "soll": required, "grund": reason}


def _result(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "fehlgeschlagen" for check in checks):
        return "nacharbeit_erforderlich"
    if any(check["status"] == "nicht_geprueft" for check in checks):
        return "pruefung_unvollstaendig"
    return "freigabefaehig"


def _word_key(word: str) -> str:
    return word.strip(".,;:!?\"'„“‚‘()[]{}").casefold()


def _is_number(word: str) -> bool:
    return bool(_NUMBER_RE.fullmatch(_word_key(word)))


def _is_unit(word: str) -> bool:
    return _word_key(word) in _UNITS


def _time_ms(groups: tuple[str, ...]) -> int:
    hours, minutes, seconds, milliseconds = map(int, groups)
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def _parse_srt(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not normalized.strip():
        return [], ["SRT enthält keine Untertitel."]
    cues = []
    errors = []
    for block_number, block in enumerate(re.split(r"\n[ \t]*\n+", normalized), 1):
        if not block.strip():
            continue
        lines = block.split("\n")
        if len(lines) < 3 or not re.fullmatch(r"\d+", lines[0]):
            errors.append(f"Block {block_number}: Nummer, Zeitzeile oder Text fehlt/ist ungültig.")
            continue
        match = _TIME_RE.fullmatch(lines[1])
        if not match:
            errors.append(f"Block {block_number}: ungültige SRT-Zeitzeile.")
            continue
        content = lines[2:]
        if any(not line.strip() for line in content):
            errors.append(f"Block {block_number}: leere Textzeile.")
            continue
        start_ms = _time_ms(match.groups()[:4])
        end_ms = _time_ms(match.groups()[4:])
        cues.append({"id": int(lines[0]), "start_ms": start_ms, "ende_ms": end_ms,
                     "lines": content, "text": "\n".join(content),
                     "characters": sum(len(line) for line in content)})
    return cues, errors


def _split_sensitive_boundary(previous: str, following: str) -> bool:
    left = previous.split()
    right = following.split()
    if not left or not right:
        return False
    last, first = _word_key(left[-1]), _word_key(right[0])
    if last in _NEGATIONS and left[-1][-1:] not in ".!?;:":
        return True
    if _is_number(left[-1]) and (_is_unit(right[0]) or first in {"bis", "von", "–", "−", "-"}):
        return True
    if last in {"−", "-", "+"} and _is_number(right[0]):
        return True
    if last in {"bis", "von", "–", "−", "-"} and len(left) >= 2 and _is_number(left[-2]) and _is_number(right[0]):
        return True
    return False


def _font_check(cues: list[dict[str, Any]], font_path: str | Path | None) -> tuple[dict[str, Any], str | None]:
    requirement = "Jede Zeile höchstens 840 px mit echtem Montserrat Bold, 52 px (x=90…930)."
    if font_path is None:
        return _check("srt_pixel_width", "nicht_geprueft", None, requirement,
                      "Keine echte Montserrat-Bold-Schriftdatei übergeben; Zeichenanzahl ist keine Pixelmessung."), None
    source = Path(font_path).expanduser().resolve()
    try:
        font_bytes = source.read_bytes()
        font_sha = hashlib.sha256(font_bytes).hexdigest()
    except OSError as error:
        return _check("srt_pixel_width", "nicht_geprueft", None, requirement,
                      f"Schriftdatei nicht lesbar: {error}"), None
    try:
        from PIL import ImageFont
    except ImportError:
        return _check("srt_pixel_width", "nicht_geprueft", {"font_path": str(source), "font_sha256": font_sha},
                      requirement, "Pillow nicht installiert; keine echte Fontmessung verfügbar."), font_sha
    try:
        # Load exactly the hashed bytes, avoiding a changed file between hashing
        # and measurement. Pillow performs real font layout, not a char estimate.
        import io
        font = ImageFont.truetype(io.BytesIO(font_bytes), FONT_SIZE_PX)
        family, style = font.getname()
        if family.casefold() != "montserrat" or style.casefold() != "bold":
            return _check("srt_pixel_width", "nicht_geprueft",
                          {"family": family, "style": style, "font_sha256": font_sha}, requirement,
                          "Übergebene Schrift ist kein Montserrat Bold; keine Ersatzfont als Nachweis akzeptiert."), font_sha
        measured = [{"cue": cue["id"], "line": line_number, "width_px": float(font.getlength(line))}
                    for cue in cues for line_number, line in enumerate(cue["lines"], 1)]
    except (OSError, ValueError, AttributeError, TypeError) as error:
        return _check("srt_pixel_width", "nicht_geprueft", {"font_sha256": font_sha}, requirement,
                      f"Echte Fontmessung fehlgeschlagen: {error}"), font_sha
    overflows = [line for line in measured if line["width_px"] > MAX_PIXEL_WIDTH]
    return _check("srt_pixel_width", "fehlgeschlagen" if overflows else "bestanden",
                  {"font_path": str(source), "font_sha256": font_sha, "family": family, "style": style,
                   "font_size_px": FONT_SIZE_PX, "max_width_px": max((m["width_px"] for m in measured), default=0),
                   "measurements": measured, "overflows": overflows}, requirement,
                  "Fontmetriken gemessen; tatsächliche Burn-in-Position und Renderfont bleiben visuell zu prüfen."), font_sha


def validate_srt(path: str | Path, font_path: str | Path | None = None) -> dict[str, Any]:
    """Validate actual bytes and caption limits; do not invent audio alignment.

    CPS counts Unicode codepoints, including spaces, excluding line separators.
    Pixel width is measured only with a genuine Montserrat Bold font at 52 px.
    SRT alone cannot prove the 100-ms audio tolerance or rendered safe areas.
    """
    source = Path(path).expanduser().resolve()
    checks = []
    digest = None
    cues: list[dict[str, Any]] = []
    parse_errors = []
    try:
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8-sig", errors="strict")
        checks.append(_check("srt_utf8", "bestanden", {"bom": raw.startswith(b"\xef\xbb\xbf")}, "UTF-8-SRT."))
        cues, parse_errors = _parse_srt(text)
    except UnicodeDecodeError as error:
        checks.append(_check("srt_utf8", "fehlgeschlagen", None, "UTF-8-SRT.", str(error)))
        parse_errors = ["SRT ist nicht als UTF-8 lesbar."]
    except OSError as error:
        checks.append(_check("srt_utf8", "fehlgeschlagen", None, "Lesbare UTF-8-SRT.", str(error)))
        parse_errors = ["SRT-Datei nicht lesbar."]
    syntax_ok = bool(cues) and not parse_errors
    checks.append(_check("srt_syntax", "bestanden" if syntax_ok else "fehlgeschlagen",
                         parse_errors, "Gültige nummerierte SRT-Blöcke mit HH:MM:SS,mmm-Zeitzeilen."))
    font_sha = None
    if syntax_ok:
        indices = [cue["id"] for cue in cues]
        checks.append(_check("srt_index_sequence", "bestanden" if indices == list(range(1, len(cues) + 1))
                             else "fehlgeschlagen", indices, "Fortlaufende Nummern ab 1."))
        timeline_errors = []
        previous_end = 0
        for cue in cues:
            if cue["start_ms"] < previous_end or cue["start_ms"] >= cue["ende_ms"] or cue["ende_ms"] > CAPTION_END_MS:
                timeline_errors.append({"cue": cue["id"], "start_ms": cue["start_ms"], "ende_ms": cue["ende_ms"]})
            previous_end = cue["ende_ms"]
        checks.append(_check("srt_timeline", "fehlgeschlagen" if timeline_errors else "bestanden", timeline_errors,
                             "Geordnete, nicht überlappende positive Intervalle vollständig in 0…54.000 ms."))
        wrong_lines = [{"cue": cue["id"], "lines": len(cue["lines"])} for cue in cues if len(cue["lines"]) > MAX_LINES]
        checks.append(_check("srt_line_count", "fehlgeschlagen" if wrong_lines else "bestanden", wrong_lines,
                             "Höchstens zwei Zeilen pro Untertitel."))
        long_lines = [{"cue": cue["id"], "line": index, "characters": len(line)}
                      for cue in cues for index, line in enumerate(cue["lines"], 1)
                      if len(line) > MAX_LINE_CHARACTERS]
        checks.append(_check("srt_line_length", "fehlgeschlagen" if long_lines else "bestanden", long_lines,
                             "Höchstens 28 Unicode-Zeichen pro Zeile einschließlich Leerzeichen."))
        durations = [{"cue": cue["id"], "duration_ms": cue["ende_ms"] - cue["start_ms"]}
                     for cue in cues if not MIN_CUE_MS <= cue["ende_ms"] - cue["start_ms"] <= MAX_CUE_MS]
        checks.append(_check("srt_cue_duration", "fehlgeschlagen" if durations else "bestanden", durations,
                             "Standzeit 0,80…4,00 Sekunden einschließlich."))
        rates = []
        for cue in cues:
            duration = cue["ende_ms"] - cue["start_ms"]
            cps = cue["characters"] * 1000 / duration if duration > 0 else None
            cue["cps"] = cps
            if cps is None or cue["characters"] * 1000 > MAX_CPS * duration:
                rates.append({"cue": cue["id"], "cps": cps, "characters": cue["characters"]})
        checks.append(_check("srt_cps", "fehlgeschlagen" if rates else "bestanden", rates,
                             "Höchstens 18 Zeichen/s, ohne Zeilenumbrüche, einschließlich Leerzeichen."))
        styled = [{"cue": cue["id"]} for cue in cues if any(
            re.search(r"<[^>]*>|\{\\[^}]*\}", line) or any(ord(character) < 32 or character == "\ufeff" for character in line)
            for line in cue["lines"])]
        checks.append(_check("srt_plain_text", "fehlgeschlagen" if styled else "bestanden", styled,
                             "Reiner Untertiteltext ohne Styling-Tags oder Steuerzeichen."))
        boundaries = [(cue["id"], previous, following) for cue in cues
                      for previous, following in zip(cue["lines"], cue["lines"][1:])]
        boundaries.extend((right["id"], left["lines"][-1], right["lines"][0]) for left, right in zip(cues, cues[1:]))
        sensitive = [{"cue": cue_id, "before": previous, "after": following}
                     for cue_id, previous, following in boundaries if _split_sensitive_boundary(previous, following)]
        checks.append(_check("srt_semantic_wrap", "fehlgeschlagen" if sensitive else "bestanden", sensitive,
                             "Negation und folgendes Wort sowie Zahlen, Bereiche und Einheiten nicht über Umbrüche trennen.",
                             "Erkennbare sprachliche Bindungen geprüft; vollständige Sinnprüfung bleibt redaktionell."))
        font_check, font_sha = _font_check(cues, font_path)
        checks.append(font_check)
    else:
        for check_id, requirement in (
            ("srt_index_sequence", "Fortlaufende Nummern ab 1."),
            ("srt_timeline", "Untertitel vollständig in 0…54 s; keine Überlappung."),
            ("srt_line_count", "Höchstens zwei Zeilen."),
            ("srt_line_length", "Höchstens 28 Zeichen je Zeile."),
            ("srt_cue_duration", "Standzeit 0,80…4,00 s."),
            ("srt_cps", "Höchstens 18 Zeichen/s."),
            ("srt_plain_text", "Reiner Untertiteltext ohne Styling/Steuerzeichen."),
            ("srt_semantic_wrap", "Sinnvolle Umbrüche; Negationen/Zahlen/Einheiten zusammenhalten."),
            ("srt_pixel_width", "Montserrat Bold, 52 px, Zeilenbreite höchstens 840 px."),
        ):
            checks.append(_check(check_id, "nicht_geprueft", None, requirement, "Syntaxfehler verhindern eine vollständige Prüfung."))
    checks.extend([
        _check("srt_audio_sync", "nicht_geprueft", None, "Untertitel-Synchronität zum echten Audio höchstens 100 ms.",
               "SRT enthält Zeitstempel, aber kein Audio. Abgleich mit finalem Audio ist eine menschliche Pflichtprüfung."),
        _check("srt_burn_in", "nicht_geprueft", None,
               "Echte Burn-in-SRT: Montserrat Bold 52 px; x=90…930, y=192…1536, Unterkante ≤1520; Quellen y=1200…1320.",
               "Finales Video in Originalauflösung ansehen: Position, Renderfont, Lesbarkeit, Quellenkollisionen und tatsächlichen Burn-in prüfen."),
    ])
    return {"ergebnis": _result(checks), "checks": checks, "sha256": digest, "path": str(source),
            "font_sha256": font_sha, "cues": cues,
            "timing_basis": "Zeitstempel aus SRT; Audio-Synchronität nicht gemessen.",
            "manual_steps": [
                "Echte Montserrat-Bold-Fontdatei übergeben und Pixelbreite messen; Ersatzfonts liefern keinen Profilnachweis.",
                "Geschätzte Generator-Timings anhand echter finaler Audiospur korrigieren; alle Ein-/Ausblendungen auf höchstens 100 ms Abweichung prüfen.",
                "Finales Video mit eingebrannten Untertiteln ansehen und Font, Safe Areas, Quellenposition und Lesbarkeit konkret bestätigen.",
            ]}


def _atomic_phrases(text: str) -> list[str]:
    words = text.split()
    atoms = []
    index = 0
    while index < len(words):
        parts = [words[index]]
        index += 1
        if _word_key(parts[0]) in _NEGATIONS and index < len(words):
            parts.append(words[index])
            index += 1
        if _word_key(parts[-1]) in {"−", "-", "+"} and index < len(words) and _is_number(words[index]):
            parts.append(words[index])
            index += 1
        if _is_number(parts[-1]):
            # Preserve both numeric ranges and "1 von 100" denominators.
            while index + 1 < len(words) and _word_key(words[index]) in {"bis", "von", "–", "−", "-"} and _is_number(words[index + 1]):
                parts.extend(words[index:index + 2])
                index += 2
            if index < len(words) and _is_unit(words[index]):
                parts.append(words[index])
                index += 1
        atom = " ".join(parts)
        if len(atom) > MAX_LINE_CHARACTERS:
            raise ValueError(f"Unteilbare Wort-/Zahlen-/Negationsgruppe ist länger als 28 Zeichen: {atom!r}")
        atoms.append(atom)
    return atoms


def _wrap_text(text: str) -> list[list[str]]:
    atoms = _atomic_phrases(text)
    if not atoms:
        return []
    costs = [math.inf] * (len(atoms) + 1)
    breaks = [0] * len(atoms)
    costs[-1] = 0
    for start in range(len(atoms) - 1, -1, -1):
        for end in range(start + 1, len(atoms) + 1):
            line = " ".join(atoms[start:end])
            if len(line) > MAX_LINE_CHARACTERS:
                break
            punctuation_bonus = 250 if line.endswith((".", "!", "?")) else 80 if line.endswith((",", ";", ":")) else 0
            score = 400 + (MAX_LINE_CHARACTERS - len(line)) ** 2 / 2 - punctuation_bonus + costs[end]
            if score < costs[start]:
                costs[start] = score
                breaks[start] = end
    lines = []
    cursor = 0
    while cursor < len(atoms):
        end = breaks[cursor]
        if end <= cursor:
            raise ValueError("Text kann nicht semantisch innerhalb von 28 Zeichen umbrochen werden.")
        lines.append(" ".join(atoms[cursor:end]))
        cursor = end
    cues = []
    cursor = 0
    while cursor < len(lines):
        count = 1 if lines[cursor].endswith((".", "!", "?")) else min(2, len(lines) - cursor)
        cues.append(lines[cursor:cursor + count])
        cursor += count
    return cues


def _estimate_window(text: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    blocks = _wrap_text(text)
    if not blocks:
        return []
    available = end_ms - start_ms
    characters = [sum(len(line) for line in block) for block in blocks]
    durations = [max(MIN_CUE_MS, math.ceil(count * 1000 / MAX_CPS)) for count in characters]
    if sum(durations) > available or available <= 0:
        raise ValueError("Geschätztes Szenenfenster ist zu kurz für 18 CPS und mindestens 0,80 s; Text/Szenenplan überarbeiten.")
    target = min(available, len(blocks) * MAX_CUE_MS)
    extra = target - sum(durations)
    while extra > 0:
        active = [index for index, duration in enumerate(durations) if duration < MAX_CUE_MS]
        if not active:
            break
        total_weight = sum(characters[index] for index in active)
        remaining = extra
        for index in active:
            increment = min(MAX_CUE_MS - durations[index], extra,
                            max(1, int(remaining * characters[index] / total_weight)))
            durations[index] += increment
            extra -= increment
    gaps = available - sum(durations)
    result = []
    elapsed = 0
    for index, (lines, duration) in enumerate(zip(blocks, durations)):
        gap_before = round(gaps * index / (len(blocks) - 1)) if len(blocks) > 1 else 0
        cue_start = start_ms + elapsed + gap_before
        result.append({"start_ms": cue_start, "ende_ms": cue_start + duration, "lines": lines})
        elapsed += duration
    return result


def _format_time(milliseconds: int) -> str:
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def generate_srt(A05_inhalt: dict[str, Any], A06_inhalt: dict[str, Any]) -> str:
    """Generate plain SRT with **GESCHÄTZTE TIMINGS**, never measured sync.

    A05's ``untertitel_basis`` (or ``sprechertext``) is the text authority. If
    A06 has spoken scenes, their text must exactly cover that basis, ignoring
    whitespace, and their editorial windows supply the estimated bounds.
    Without spoken scenes, text is estimated across 0…54 seconds. Impossible
    line/CPS/duration constraints raise ValueError; no words are dropped or
    numbers/units/negations forcibly split. The operator must subsequently
    align to real audio and inspect the final burn-in within 100 ms.
    """
    if not isinstance(A05_inhalt, dict) or not isinstance(A06_inhalt, dict):
        raise TypeError("A05_inhalt und A06_inhalt müssen Objekte sein.")
    basis = A05_inhalt.get("untertitel_basis") or A05_inhalt.get("sprechertext")
    if not isinstance(basis, str) or not basis.strip():
        raise ValueError("A05 benötigt nichtleeren untertitel_basis/Sprechertext.")
    basis = " ".join(basis.split())
    scene_input = A06_inhalt.get("szenen", [])
    if not isinstance(scene_input, list):
        raise ValueError("A06.szenen muss eine Liste sein.")
    spoken_scenes = []
    previous_end = 0
    for scene in scene_input:
        if not isinstance(scene, dict):
            raise ValueError("Jede A06-Szene muss ein Objekt sein.")
        spoken = scene.get("sprechertext", "")
        if not isinstance(spoken, str):
            raise ValueError("Szenen-Sprechertext muss Text sein.")
        if not spoken.strip():
            continue
        start, end = scene.get("start_ms"), scene.get("ende_ms")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= CAPTION_END_MS or start < previous_end:
            raise ValueError("Gesprochene A06-Szenen benötigen geordnete, nicht überlappende Fenster innerhalb 0…54 s.")
        previous_end = end
        spoken_scenes.append((" ".join(spoken.split()), start, end))
    if spoken_scenes and " ".join(scene[0] for scene in spoken_scenes) != basis:
        raise ValueError("A06-Sprechertext stimmt nicht vollständig mit A05-Untertitelbasis überein; kein abweichender Text wird erfunden.")
    # With no scene plan, do not stretch a short sentence across 54 seconds.
    # 15 CPS is merely an editorial timing estimate, expressly not a voice or
    # sync measurement. Long narration still has the hard 54-second boundary.
    default_blocks = _wrap_text(basis) if not spoken_scenes else []
    default_duration = min(CAPTION_END_MS, max(len(default_blocks) * MIN_CUE_MS,
                                              math.ceil(len(basis) * 1000 / 15)))
    windows = spoken_scenes or [(basis, 0, default_duration)]
    cues = []
    for text, start, end in windows:
        cues.extend(_estimate_window(text, start, end))
    blocks = [f"{index}\n{_format_time(cue['start_ms'])} --> {_format_time(cue['ende_ms'])}\n" + "\n".join(cue["lines"])
              for index, cue in enumerate(cues, 1)]
    return "\n\n".join(blocks) + "\n"
