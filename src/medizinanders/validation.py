"""Deterministic artifact checks; these checks never grant a human approval.

Only the supplied JSON is inspected. Opening and hashing actual original files,
media measurements and human attestations belong to the orchestrator and the
media modules. A source flag is consequently necessary, but is not itself proof
that a source was opened. Validation never changes an artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "A01": (),
    "A02": ("A01",),
    "A03": ("A01", "A02"),
    "A04": ("A03",),
    "A05": ("A03", "A04"),
    "A06": ("A03", "A04", "A05"),
    "A07": ("A01", "A02", "A03", "A04", "A05", "A06"),
    "A08": ("A07",),
    "A09": ("A05", "A06", "A08"),
    "A10": ("A07", "A08", "A09"),
    "A11": ("A05", "A10"),
    "A12": ("A11",),
}

TIMELINE: tuple[tuple[str, int, int], ...] = (
    ("Hook", 0, 3000),
    ("Open Loop", 3000, 8000),
    ("Payload", 8000, 41000),
    ("Verdichtung", 41000, 48000),
    ("CTA", 48000, 52000),
    ("Ausklang", 52000, 54000),
    ("Disclaimer", 54000, 58000),
)

A07_REQUIRED_CHECKS: tuple[str, ...] = (
    "claim_sentence_map",
    "sources_originals",
    "counterevidence_uncertainty",
    "medical_legal_escalation",
    "timeline_cta_disclaimer",
    "assets_rights",
    "invideo_complete",
)

A10_REQUIRED_CHECKS: tuple[str, ...] = (
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

MANUAL_TECHNICAL_CHECKS: frozenset[str] = frozenset({
    "video_bitrate_target", "video_vbv_maxrate", "audio_bitrate",
    "ending_visual_disclaimer", "audio_video_sync",
})

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_WORD = re.compile(r"[^\W_]+(?:[’'\-][^\W_]+|(?<=\d)[,.](?=\d)[^\W_]+)*", re.UNICODE)
_MEDICAL = re.compile(
    r"\b(?:medizin\w*|medikament\w*|arznei\w*|wirkstoff\w*|dosier\w*|dosis\w*|"
    r"nebenwirk\w*|kontraindik\w*|diagnos\w*|therap\w*|behandl\w*|heil\w*|"
    r"krank\w*|patient\w*|krebs\w*|diabet\w*|blut\w*|impf\w*|infekt\w*|"
    r"klinisch\w*|gesundheit\w*|schmerz\w*|depress\w*|sterblich\w*|mortal\w*|"
    r"präven\w*|praeven\w*|verschreib\w*|absetz\w*|nutzen.risiko\w*|"
    r"wirksam\w*|überleb\w*|ueberleb\w*|herz\w*|lunge\w*|tumor\w*|"
    r"antibiotik\w*|antidepress\w*|schwanger\w*|nahrungsergänz\w*|"
    r"nahrungsergaenz\w*|vitamin\w*|hormon\w*|insulin\w*|leber\w*|niere\w*|"
    r"placebo\w*|paracetamol\w*|ibuprofen\w*|aspirin\w*|metformin\w*|statin\w*|"
    r"semaglutid\w*|ozempic\w*|wegovy\w*|opioid\w*|covid\w*|alzheimer\w*|"
    r"demenz\w*|osteopor\w*|asthma\w*|todes\w*|tödlich\w*|toedlich\w*|"
    r"lebenserwart\w*)\b",
    re.IGNORECASE,
)
_LEGAL = re.compile(
    r"\b(?:recht\w*|jurist\w*|juris\w*|gesetz\w*|werb\w*|sponsor\w*|"
    r"datenschutz\w*|patientendaten\w*|personenbezogen\w*|urheber\w*|"
    r"lizenz\w*|persönlichkeits\w*|persoenlichkeits\w*|einwillig\w*|"
    r"stimmkop\w*|stimmimit\w*|voice.clon\w*|betrug\w*|korrupt\w*)\b",
    re.IGNORECASE,
)
_EFFECT = re.compile(
    r"\b(?:heilt|senkt|erhöht|erhoeht|wirkt|verursacht|reduziert|verbessert|"
    r"verhindert|beweist|führt|fuehrt|schützt|schuetzt|garantiert|ist sicher)\b",
    re.IGNORECASE,
)
_FACT_DATA = re.compile(r"\d+(?:[,.]\d+)?\s*(?:%|prozent\b|mg\b|milligramm\b|fälle\b|faelle\b)", re.IGNORECASE)
_FACT_SOURCE = re.compile(r"\b(?:eine|die|diese|laut(?: einer| der)?)\s+studie\b.*\b(?:zeigt|belegt|ergibt|bestätigt|bestaetigt)\b", re.IGNORECASE)
_EXTRA_CTA = re.compile(
    r"\b(?:abonniere|abonniert|kommentiere|kommentiert|klicke|klickt|like|liken|"
    r"speichere|speichert|teile (?:das|diesen|es)|folge (?:uns|mir)|"
    r"schreib(?:e)? (?:uns|mir|in die|einen))\b",
    re.IGNORECASE,
)
_AI = re.compile(r"\b(?:ki|ai)\b|generativ|ki.generiert|ai.generated", re.IGNORECASE)
_IMITATION = re.compile(r"\b(?:stimmkop\w*|stimmklon\w*|stimmimit\w*|voice[\s_-]*clon\w*|voice[\s_-]*imit\w*|imitierte[\s_-]+stimme)\b", re.IGNORECASE)
_SIMULATION = re.compile(r"\b(?:dem[o0]_simulation|simulation|simuliert|fiktiv|platzhalter)\b", re.IGNORECASE)
_SHA_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def count_words(text: str) -> int:
    """Count Unicode words; compounds and decimal numbers count as one word."""
    return len(_WORD.findall(text)) if isinstance(text, str) else 0


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def _normalized(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", _text(value).casefold(), flags=re.UNICODE).strip()


def _function(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _text(value).casefold())


def _objects(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _content(artifacts: Mapping[str, Any], artifact_id: str) -> Mapping[str, Any]:
    artifact = artifacts.get(artifact_id)
    if not isinstance(artifact, Mapping):
        return {}
    content = artifact.get("inhalt")
    return content if isinstance(content, Mapping) else {}


def _ids(items: Any) -> dict[str, Mapping[str, Any]]:
    return {item["id"]: item for item in _objects(items) if isinstance(item.get("id"), str)}


def _deduplicate(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))


def _nonstring_keys(value: Any, path: str) -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                errors.append(f"{path}: JSON-Objektschlüssel müssen Zeichenfolgen sein.")
            errors.extend(_nonstring_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            errors.extend(_nonstring_keys(item, f"{path}[{i}]"))
    return errors


def _artifact_hash(data: Mapping[str, Any]) -> str:
    encoded = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _format_checker() -> FormatChecker:
    # jsonschema's built-in RFC3339 checker is an optional dependency. ISO dates
    # must still be checked when only the contracted jsonschema/PyYAML are present.
    checker = FormatChecker()

    @checker.checks("date-time", raises=(ValueError, TypeError))
    def iso_datetime(value: Any) -> bool:
        if not isinstance(value, str):
            return True
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value):
            return False
        datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
        return True

    @checker.checks("date", raises=(ValueError, TypeError))
    def iso_date(value: Any) -> bool:
        if not isinstance(value, str):
            return True
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return False
        date.fromisoformat(value)
        return True

    return checker


@lru_cache(maxsize=1)
def _validators() -> dict[str, Draft202012Validator]:
    files = [_SCHEMA_DIR / "common.schema.json"] + [_SCHEMA_DIR / f"{aid}.schema.json" for aid in DEPENDENCIES]
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas)
    return {
        aid: Draft202012Validator(schema, registry=registry, format_checker=_format_checker())
        for aid, schema in zip(DEPENDENCIES, schemas[1:])
    }


def _schema_message(aid: str, error: Any) -> str:
    path = aid + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
    rule = error.validator
    if rule == "required":
        missing = [name for name in error.validator_value if name not in error.instance]
        return f"{path}: Pflichtfeld {', '.join(missing)} fehlt."
    if rule == "additionalProperties":
        known = error.schema.get("properties", {})
        extra = sorted(str(name) for name in error.instance if name not in known)
        return f"{path}: Unbekannte Felder: {', '.join(extra)}."
    if rule == "type":
        names = {"object": "Objekt", "array": "Liste", "string": "Zeichenfolge", "integer": "Ganzzahl", "number": "Zahl", "boolean": "Boolescher Wert", "null": "null"}
        expected = error.validator_value
        expected = "/".join(names.get(item, item) for item in expected) if isinstance(expected, list) else names.get(expected, expected)
        return f"{path}: Erwarteter Typ: {expected}."
    if rule == "enum":
        return f"{path}: Ungültiger Wert; zulässig: {', '.join(str(value) for value in error.validator_value)}."
    if rule == "const":
        return f"{path}: Erwarteter fester Wert: {error.validator_value!r}."
    if rule == "format":
        return f"{path}: Ungültiges Format {error.validator_value}; ISO8601 bzw. gültige URI verwenden."
    if rule == "pattern":
        if path.endswith(".version"):
            return f"{path}: Gültige SemVer-Version erwartet, etwa 1.2.3 oder 1.2.3-rc.1."
        if path.endswith(".sha256") or path.endswith("_sha256"):
            return f"{path}: SHA-256 muss aus genau 64 kleinen Hexadezimalzeichen bestehen."
        return f"{path}: Wert entspricht nicht dem vorgeschriebenen Muster."
    if rule in {"minLength", "minProperties"}:
        return f"{path}: Pflichtangabe darf nicht leer sein."
    if rule == "uniqueItems":
        return f"{path}: Doppelte Einträge sind nicht zulässig."
    if rule in {"minItems", "maxItems"}:
        relation = "mindestens" if rule == "minItems" else "höchstens"
        return f"{path}: Liste muss {relation} {error.validator_value} Einträge enthalten."
    if rule in {"minimum", "maximum"}:
        relation = "mindestens" if rule == "minimum" else "höchstens"
        return f"{path}: Wert muss {relation} {error.validator_value} sein."
    if rule in {"anyOf", "oneOf"}:
        return f"{path}: Kein zulässiger Typ oder kein gültiges Format; null ist nur ausdrücklich erlaubten Feldern gestattet."
    return f"{path}: Schemaanforderung {rule} ist nicht erfüllt."


def _normalize_bundle(artifacts: Any) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    errors: list[str] = []
    result: dict[str, Mapping[str, Any]] = {}
    if isinstance(artifacts, Mapping):
        pairs = list(artifacts.items())
    elif isinstance(artifacts, Sequence) and not isinstance(artifacts, (str, bytes, bytearray)):
        pairs = [(item.get("artefakt_id") if isinstance(item, Mapping) else None, item) for item in artifacts]
    else:
        return {}, ["Artefaktbundle muss ein Objekt nach Artefakt-ID oder eine Liste von Artefakten sein."]
    for key, artifact in pairs:
        if not isinstance(artifact, Mapping):
            errors.append(f"Bundle[{key!r}]: Artefakt muss ein JSON-Objekt sein.")
            continue
        aid = artifact.get("artefakt_id")
        if not isinstance(aid, str) or aid not in DEPENDENCIES:
            errors.append(f"Bundle[{key!r}]: artefakt_id muss A01 bis A12 sein.")
            continue
        if key != aid:
            errors.append(f"Bundle[{key!r}]: Schlüssel passt nicht zur artefakt_id {aid}.")
        if aid in result:
            errors.append(f"Bundle: Artefakt-ID {aid} ist doppelt enthalten.")
        else:
            result[aid] = artifact
    return result, errors


def _unique_ids(items: Any, path: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for item in _objects(items):
        identifier = item.get("id")
        if isinstance(identifier, str):
            if identifier in seen:
                errors.append(f"{path}: ID {identifier!r} ist doppelt enthalten.")
            seen.add(identifier)


def _validate_common(data: Mapping[str, Any], index: Mapping[str, Any], contextual: bool, production: bool, errors: list[str]) -> None:
    aid = data["artefakt_id"]
    project = data.get("projekt_id")
    if isinstance(project, str) and re.fullmatch(r"MA-\d{8}-\d{3}", project):
        try:
            datetime.strptime(project[3:11], "%Y%m%d")
        except ValueError:
            errors.append(f"{aid}.projekt_id: Datum in der Projekt-ID ist ungültig.")
    if data.get("gesperrt") is True:
        if not _text(data.get("sperrgrund")):
            errors.append(f"{aid}: Gesperrtes Artefakt benötigt einen konkreten Sperrgrund.")
        if production or data.get("status") in {"freigegeben", "produziert", "veröffentlicht"}:
            errors.append(f"{aid}: Artefakt ist gesperrt und darf nicht produktiv verwendet werden: {_text(data.get('sperrgrund'))}.")
    elif data.get("gesperrt") is False and data.get("sperrgrund") is not None:
        errors.append(f"{aid}: sperrgrund muss bei einem ungesperrten Artefakt null sein.")
    if production and data.get("beispiel") is True:
        errors.append(f"{aid}: DEMO-Artefakt ist für Produktion und Veröffentlichung gesperrt.")
    if production and _strings(data.get("offene_punkte")):
        errors.append(f"{aid}: Offene Punkte müssen vor produktiver Verwendung geklärt werden.")
    entries = _objects(data.get("eingaben"))
    actual = [entry.get("artefakt_id") for entry in entries]
    required = set(DEPENDENCIES[aid])
    if len(actual) != len(set(str(value) for value in actual)):
        errors.append(f"{aid}.eingaben: Abhängigkeits-IDs dürfen nicht doppelt vorkommen.")
    missing = sorted(required - set(str(value) for value in actual))
    unexpected = sorted(set(str(value) for value in actual) - required)
    if missing:
        errors.append(f"{aid}.eingaben: Pflichtabhängigkeiten fehlen: {', '.join(missing)}.")
    if unexpected:
        errors.append(f"{aid}.eingaben: Unzulässige Abhängigkeiten: {', '.join(unexpected)}.")
    if production and required and not contextual:
        errors.append(f"{aid}: Für die Produktionsprüfung müssen die abhängigen Artefakte vorliegen.")
    if contextual:
        for entry in entries:
            dep_id = entry.get("artefakt_id")
            if not isinstance(dep_id, str) or dep_id not in required:
                continue
            dependency = index.get(dep_id)
            if not isinstance(dependency, Mapping):
                errors.append(f"{aid}.eingaben: Abhängiges Artefakt {dep_id} fehlt im Bundle.")
                continue
            if dependency.get("projekt_id") != project:
                errors.append(f"{aid}.eingaben: {dep_id} gehört zu einem anderen Projekt.")
            if dependency.get("version") != entry.get("version"):
                errors.append(f"{aid}.eingaben: Version von {dep_id} stimmt nicht mit dem referenzierten Artefakt überein.")
            try:
                expected_hash = _artifact_hash(dependency)
            except (TypeError, ValueError):
                continue
            if entry.get("sha256") != expected_hash:
                errors.append(f"{aid}.eingaben: SHA-256 von {dep_id} stimmt nicht mit dem unveränderlichen Eingabeartefakt überein.")
    sources = _ids(_content(index, "A02").get("sources"))
    if sources:
        for source_id in _strings(data.get("quellen")):
            if source_id not in sources:
                errors.append(f"{aid}.quellen: Unbekannte Quellen-ID {source_id!r}.")
    elif contextual and _strings(data.get("quellen")):
        errors.append(f"{aid}.quellen: Quellenreferenzen sind ohne A02-Quellenpaket nicht prüfbar.")


def _validate_sources(content: Mapping[str, Any], production: bool, errors: list[str]) -> None:
    _unique_ids(content.get("sources"), "A02.inhalt.sources", errors)
    for source in _objects(content.get("sources")):
        path = f"A02.Quelle {source.get('id', '?')}"
        if source.get("zugriff") == "geprueft":
            if source.get("original_geoeffnet") is not True:
                errors.append(f"{path}: Suchtreffer oder Metadaten gelten nicht als geprüftes Original; original_geoeffnet muss wahr sein.")
            if not _text(source.get("fundstelle")):
                errors.append(f"{path}: Für ein geprüftes Original ist eine konkrete Fundstelle erforderlich.")
            if production and (not _text(source.get("lokaler_pfad")) or not _text(source.get("sha256"))):
                errors.append(f"{path}: Produktive Originalprüfung benötigt lokalen Pfad und SHA-256; Zugriffsflags allein sind kein Nachweis.")


def _review_needs(content: Mapping[str, Any]) -> tuple[bool, bool]:
    medical = False
    legal = False
    for claim in _objects(content.get("claims")):
        # Attribution as a Quellenbehauptung never cancels a medical risk.
        context = " ".join([_text(claim.get("text")), _text(claim.get("art")), *_strings(claim.get("risiken"))])
        medical |= claim.get("medizinisch_relevant") is True or bool(_MEDICAL.search(context))
        legal |= claim.get("rechtlich_relevant") is True or bool(_LEGAL.search(context))
    overview = content.get("risikoübersicht")
    if isinstance(overview, list):
        try:
            risk_text = json.dumps(overview, ensure_ascii=False)
        except (TypeError, ValueError):
            risk_text = ""
        medical |= bool(_MEDICAL.search(risk_text))
        legal |= bool(_LEGAL.search(risk_text))
    return medical, legal


def _validate_claims(content: Mapping[str, Any], index: Mapping[str, Any], contextual: bool, production: bool, errors: list[str]) -> None:
    _unique_ids(content.get("claims"), "A03.inhalt.claims", errors)
    sources = _ids(_content(index, "A02").get("sources"))
    for claim in _objects(content.get("claims")):
        path = f"A03.Claim {claim.get('id', '?')}"
        status = claim.get("status")
        use = claim.get("einsatz")
        if status in {"WIDERLEGT", "UNBEWIESEN"} and use != "nein":
            errors.append(f"{path}: {status} darf nicht eingesetzt werden; einsatz muss nein sein.")
        if status == "TEILWEISE" and use == "ja":
            errors.append(f"{path}: TEILWEISE darf nur mit Einschränkung oder gar nicht eingesetzt werden.")
        if use == "nur_mit_einschraenkung" and not _strings(claim.get("einschraenkungen")):
            errors.append(f"{path}: Eingeschränkter Einsatz benötigt ausdrückliche Einschränkungen.")
        source_ids = _strings(claim.get("source_ids"))
        if status in {"BESTÄTIGT", "TEILWEISE"}:
            if not source_ids or not _strings(claim.get("fundstellen")):
                errors.append(f"{path}: BESTÄTIGT/TEILWEISE benötigt Quellen-IDs und konkrete Fundstellen.")
            if (contextual or production) and not sources:
                errors.append(f"{path}: Ohne zugängliches A02-Originalpaket ist keine Bestätigung möglich.")
        for source_id in source_ids:
            source = sources.get(source_id)
            if source is None:
                if contextual or production:
                    errors.append(f"{path}: Unbekannte Quellen-ID {source_id!r}.")
                continue
            if status in {"BESTÄTIGT", "TEILWEISE"}:
                if source.get("zugriff") != "geprueft" or source.get("original_geoeffnet") is not True or not _text(source.get("fundstelle")):
                    errors.append(f"{path}: Quelle {source_id} wurde nicht am Original geprüft; keine Bestätigung aus Suchtreffern, Abstracts oder nicht zugänglichen Quellen.")
                if _AI.search(_text(source.get("typ"))):
                    errors.append(f"{path}: KI-generierte Quelle {source_id} ist kein Originalnachweis für einen bestätigten Claim.")
                if production and (not _text(source.get("lokaler_pfad")) or not _text(source.get("sha256"))):
                    errors.append(f"{path}: Originalbeleg {source_id} ist ohne lokalen Pfad und SHA-256 nicht produktiv nachprüfbar.")
    medical, legal = _review_needs(content)
    if medical and content.get("medical_review_required") is not True:
        errors.append("A03: Medizinische Claims oder Risiken erfordern medical_review_required=true; ein false-Relevanzflag umgeht die Eskalation nicht.")
    if legal and content.get("legal_review_required") is not True:
        errors.append("A03: Rechtliche Claims oder Risiken erfordern legal_review_required=true; ein false-Relevanzflag umgeht die Eskalation nicht.")


def _claim_usage(claim_id: str, claims: Mapping[str, Any], path: str, contextual: bool, errors: list[str]) -> Mapping[str, Any] | None:
    claim = claims.get(claim_id)
    if not isinstance(claim, Mapping):
        if contextual:
            errors.append(f"{path}: Unbekannte Claim-ID {claim_id!r}.")
        return None
    if claim.get("einsatz") == "nein" or claim.get("status") in {"WIDERLEGT", "UNBEWIESEN"}:
        errors.append(f"{path}: Claim {claim_id} ist gesperrt bzw. nicht belegbar und darf nicht eingesetzt werden.")
    if claim.get("status") == "TEILWEISE" and claim.get("einsatz") != "nur_mit_einschraenkung":
        errors.append(f"{path}: Teilweise belegter Claim {claim_id} hat keinen zulässigen eingeschränkten Einsatz.")
    return claim


def _validate_statement(statement: Mapping[str, Any], claims: Mapping[str, Any], path: str, contextual: bool, errors: list[str], *, restrictions: bool = True) -> None:
    refs = _strings(statement.get("claim_ids"))
    text = _text(statement.get("text"))
    if statement.get("faktisch") is True and not refs:
        errors.append(f"{path}: Jede faktische Aussage benötigt mindestens eine Claim-ID.")
    if statement.get("faktisch") is False:
        if refs:
            errors.append(f"{path}: Claim-IDs erfordern faktisch=true; Fakten dürfen nicht als nichtfaktisch markiert werden.")
        known_fact = any(_normalized(claim.get("text")) == _normalized(text) and text for claim in claims.values())
        obvious_fact = bool(_FACT_DATA.search(text) or _FACT_SOURCE.search(text) or (_MEDICAL.search(text) and _EFFECT.search(text)))
        if known_fact or obvious_fact:
            errors.append(f"{path}: Erkennbare Tatsachenbehauptung ist als nichtfaktisch markiert; Faktizität und Claim-IDs korrigieren.")
    for claim_id in refs:
        claim = _claim_usage(claim_id, claims, path, contextual, errors)
        if claim is not None and restrictions and claim.get("einsatz") == "nur_mit_einschraenkung":
            for limit in _strings(claim.get("einschraenkungen")):
                if _normalized(limit) not in _normalized(text):
                    errors.append(f"{path}: Einschränkung von Claim {claim_id} fehlt im sichtbaren/gesprochenen Text: {limit}.")


def _validate_timeline(content: Mapping[str, Any], errors: list[str]) -> None:
    sections = _objects(content.get("abschnitte"))
    if len(sections) != len(TIMELINE):
        errors.append("A04: Das Profil benötigt genau sieben feste Abschnitte von 0 bis 58000 ms.")
        return
    for i, (expected, section) in enumerate(zip(TIMELINE, sections)):
        function, start, end = expected
        if (_function(section.get("funktion")), section.get("start_ms"), section.get("ende_ms")) != (_function(function), start, end):
            errors.append(f"A04.abschnitte[{i}]: {function} muss exakt {start}–{end} ms belegen; Reihenfolge und Grenzen sind fest.")
    if content.get("cta_anzahl") != 1:
        errors.append("A04: Es ist genau eine CTA zulässig.")


def _citation_ids(citations: Any, sources: Mapping[str, Any]) -> set[str]:
    matched: set[str] = set()
    for citation in citations if isinstance(citations, list) else []:
        if isinstance(citation, str):
            rendered = citation
        elif isinstance(citation, Mapping):
            rendered = " ".join(str(value) for value in citation.values() if isinstance(value, (str, int, float)))
        else:
            continue
        for source_id, source in sources.items():
            if re.search(r"(?<![\w-])" + re.escape(source_id) + r"(?![\w-])", rendered) or (_text(source.get("url")) and _text(source.get("url")) in rendered):
                matched.add(source_id)
    return matched


def _validate_script(content: Mapping[str, Any], index: Mapping[str, Any], contextual: bool, errors: list[str]) -> None:
    script = _text(content.get("sprechertext"))
    sentences = _objects(content.get("saetze"))
    _unique_ids(content.get("saetze"), "A05.inhalt.saetze", errors)
    words = count_words(script)
    if not 100 <= words <= 130:
        errors.append(f"A05: Sprechertext hat {words} Wörter; vorgeschrieben sind 100–130 Wörter ohne Disclaimer.")
    if content.get("wortzahl") != words:
        errors.append(f"A05.wortzahl: Angegeben {content.get('wortzahl')!r}, tatsächlich {words}; Wortzahl darf nicht erfunden werden.")
    joined = " ".join(_text(sentence.get("text")) for sentence in sentences)
    if script != joined:
        errors.append("A05: Sprechertext und in Reihenfolge zusammengefügte Sätze sind nicht wortgetreu identisch.")
    if _text(content.get("untertitel_basis")) != script:
        errors.append("A05.untertitel_basis: Untertitelbasis muss mit dem Sprechertext wortgetreu identisch sein.")
    disclaimer = _text(content.get("disclaimer"))
    if disclaimer and disclaimer in script:
        errors.append("A05: Disclaimer ist ausschließlich eine stille Einblendung von 54000 bis 58000 ms und darf nicht im Sprechertext stehen.")
    cta = content.get("cta") if isinstance(content.get("cta"), Mapping) else {}
    cta_sentences = [sentence for sentence in sentences if _function(sentence.get("funktion")) == "cta"]
    if len(cta_sentences) != 1:
        errors.append("A05: Genau ein Satz muss die Funktion CTA tragen.")
    if cta_sentences and _text(cta_sentences[0].get("text")) != _text(cta.get("text")):
        errors.append("A05.cta: CTA-Text muss identisch mit dem einzigen CTA-Satz sein.")
    cta_text = _text(cta.get("text"))
    if cta_text and script.count(cta_text) != 1:
        errors.append("A05: Der CTA-Text muss genau einmal im Sprechertext vorkommen.")
    for sentence in sentences:
        if _function(sentence.get("funktion")) != "cta" and _EXTRA_CTA.search(_text(sentence.get("text"))):
            errors.append(f"A05.Satz {sentence.get('id', '?')}: Weitere erkennbare CTA außerhalb des CTA-Satzes ist nicht zulässig.")
        if _function(sentence.get("funktion")) == "disclaimer":
            errors.append("A05.saetze: Der stille Disclaimer darf kein gesprochener Satz sein.")
    claims = _ids(_content(index, "A03").get("claims"))
    claim_context = contextual and "A03" in index
    by_claim: dict[str, list[str]] = {}
    for i, sentence in enumerate(sentences):
        _validate_statement(sentence, claims, f"A05.saetze[{i}]", claim_context, errors, restrictions=False)
        for claim_id in _strings(sentence.get("claim_ids")):
            by_claim.setdefault(claim_id, []).append(_text(sentence.get("text")))
    for claim_id, texts in by_claim.items():
        claim = claims.get(claim_id, {})
        if claim.get("einsatz") == "nur_mit_einschraenkung":
            spoken_context = _normalized(" ".join(texts))
            for limit in _strings(claim.get("einschraenkungen")):
                if _normalized(limit) not in spoken_context:
                    errors.append(f"A05.saetze: Gesprochene Einschränkung von Claim {claim_id} fehlt: {limit}.")
    for field in ("titel", "thumbnail", "beschreibung", "cta"):
        statement = content.get(field)
        if isinstance(statement, Mapping):
            _validate_statement(statement, claims, f"A05.{field}", claim_context, errors)
    for i, overlay in enumerate(_objects(content.get("overlays"))):
        _validate_statement(overlay, claims, f"A05.overlays[{i}]", claim_context, errors)
        start, end = overlay.get("start_ms"), overlay.get("ende_ms")
        if isinstance(start, int) and isinstance(end, int):
            if start >= end:
                errors.append(f"A05.overlays[{i}]: Einblendung benötigt ein positives Zeitintervall.")
            if end > 54000 and _text(overlay.get("text")) != disclaimer:
                errors.append(f"A05.overlays[{i}]: Von 54000 bis 58000 ms ist ausschließlich der feste Disclaimer zulässig.")
    sources = _ids(_content(index, "A02").get("sources"))
    if sources and claim_context:
        used: set[str] = set(by_claim)
        for field in ("titel", "thumbnail", "beschreibung", "cta"):
            statement = content.get(field)
            if isinstance(statement, Mapping):
                used.update(_strings(statement.get("claim_ids")))
        for overlay in _objects(content.get("overlays")):
            used.update(_strings(overlay.get("claim_ids")))
        expected_sources = {source for claim_id in used for source in _strings(claims.get(claim_id, {}).get("source_ids"))}
        missing = expected_sources - _citation_ids(content.get("quellenangaben"), sources)
        if missing:
            errors.append(f"A05.quellenangaben: Nachprüfbare Quellenangaben für verwendete Claims fehlen: {', '.join(sorted(missing))}.")


def _validate_scene_claims(scenes: list[Mapping[str, Any]], script: Mapping[str, Any], errors: list[str]) -> None:
    scene_spans: list[tuple[Mapping[str, Any], int, int]] = []
    offset = 0
    for scene in scenes:
        spoken = _text(scene.get("sprechertext"))
        if spoken:
            scene_spans.append((scene, offset, offset + len(spoken)))
            offset += len(spoken) + 1
    offset = 0
    for sentence in _objects(script.get("saetze")):
        text = _text(sentence.get("text"))
        end = offset + len(text)
        if sentence.get("faktisch") is True:
            required = set(_strings(sentence.get("claim_ids")))
            for scene, start, scene_end in scene_spans:
                if start < end and scene_end > offset:
                    missing = required - set(_strings(scene.get("claim_ids")))
                    if missing:
                        errors.append(f"A06.Szene {scene.get('id', '?')}: Claim-IDs für den faktischen Sprechertext fehlen: {', '.join(sorted(missing))}.")
        offset = end + 1


def _validate_storyboard(content: Mapping[str, Any], data: Mapping[str, Any], index: Mapping[str, Any], contextual: bool, production: bool, errors: list[str]) -> None:
    scenes = _objects(content.get("szenen"))
    _unique_ids(content.get("szenen"), "A06.inhalt.szenen", errors)
    _unique_ids(content.get("assets"), "A06.inhalt.assets", errors)
    assets = _ids(content.get("assets"))
    claims = _ids(_content(index, "A03").get("claims"))
    script = _content(index, "A05")
    if scenes:
        if scenes[0].get("start_ms") != 0 or scenes[-1].get("ende_ms") != 58000:
            errors.append("A06: Szenen müssen lückenlos bei 0 ms beginnen und bei 58000 ms enden.")
    previous_end: Any = 0
    for scene in scenes:
        path = f"A06.Szene {scene.get('id', '?')}"
        start, end = scene.get("start_ms"), scene.get("ende_ms")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            continue
        if start != previous_end:
            errors.append(f"{path}: Lücke, Überlappung oder falsche Reihenfolge; Start muss {previous_end} ms sein.")
        previous_end = end
        if start >= end or start < 0 or end > 58000:
            errors.append(f"{path}: Zeitintervall muss positiv und innerhalb 0–58000 ms liegen.")
        segment = next((item for item in TIMELINE if item[1] <= start < end <= item[2]), None)
        if segment is None:
            errors.append(f"{path}: Szene darf keine Grenze der sieben festen Profilabschnitte überschreiten.")
        elif _function(scene.get("funktion")) != _function(segment[0]):
            errors.append(f"{path}: Funktion muss im Zeitintervall {segment[0]} sein.")
        if start == 3000 and _function(scene.get("uebergang")) != "harterschnitt":
            errors.append(f"{path}: Hook endet bei 3000 ms mit einem harten Schnitt; uebergang muss 'harter Schnitt' sein.")
        audio = scene.get("audio") if isinstance(scene.get("audio"), Mapping) else {}
        spoken = _text(scene.get("sprechertext"))
        if spoken and audio.get("voiceover") is not True:
            errors.append(f"{path}: Sprechertext darf nicht mit abgeschaltetem Voiceover versehen sein.")
        if start >= 54000:
            if spoken or audio.get("voiceover") is not False or audio.get("musik") is not False:
                errors.append(f"{path}: Disclaimer von 54000 bis 58000 ms ist vollständig ohne Sprechertext, Voiceover und Musik.")
            if script and _text(scene.get("overlay")) != _text(script.get("disclaimer")):
                errors.append(f"{path}: Der feste A05-Disclaimer muss von 54000 bis 58000 ms sichtbar bleiben.")
        elif script and _text(scene.get("overlay")):
            rendered = _text(scene.get("overlay"))
            matching = [overlay for overlay in _objects(script.get("overlays")) if _text(overlay.get("text")) == rendered and isinstance(overlay.get("start_ms"), int) and isinstance(overlay.get("ende_ms"), int) and overlay["start_ms"] <= start and overlay["ende_ms"] >= end]
            if not matching:
                errors.append(f"{path}: Sichtbares Overlay benötigt ein zeitlich passendes A05-Statement mit faktisch und Claim-IDs.")
        for claim_id in _strings(scene.get("claim_ids")):
            _claim_usage(claim_id, claims, path, contextual and "A03" in index, errors)
        for asset_id in _strings(scene.get("assets")):
            asset = assets.get(asset_id)
            if asset is None:
                errors.append(f"{path}: Unbekannte Asset-ID {asset_id!r}.")
            elif asset.get("ki_illustration") is True:
                label = _text(asset.get("kennzeichnung"))
                if not label or label not in _text(scene.get("overlay")):
                    errors.append(f"{path}: KI-Illustration {asset_id} benötigt ihre sichtbare Kennzeichnung im Overlay.")
    if not any(scene.get("start_ms") == 3000 for scene in scenes):
        errors.append("A06: Der harte Hook-Schnitt bei genau 3000 ms fehlt.")
    for asset in assets.values():
        path = f"A06.Asset {asset.get('id', '?')}"
        provenance = " ".join([_text(asset.get("typ")), _text(asset.get("herkunft"))])
        if asset.get("imitierte_stimme") is True or _IMITATION.search(provenance):
            errors.append(f"{path}: Imitierte reale Stimmen sind verboten und blockieren das Artefakt; eine Einwilligung ist keine Ausnahme.")
        if asset.get("recht_status") == "geklaert" and not _text(asset.get("nachweis")):
            errors.append(f"{path}: Geklärte Rechte benötigen einen konkreten Rechtebeleg.")
        if asset.get("recht_status") != "geklaert" and production:
            errors.append(f"{path}: Offene Assetrechte blockieren Produktion und Veröffentlichung.")
        if _AI.search(provenance) and asset.get("ki_illustration") is not True:
            errors.append(f"{path}: Erkennbar KI-erzeugtes Material muss als ki_illustration=true erfasst werden.")
        if asset.get("ki_illustration") is True and not _text(asset.get("kennzeichnung")):
            errors.append(f"{path}: KI-Illustration benötigt eine ausdrückliche sichtbare Kennzeichnung.")
    if script:
        spoken = " ".join(_text(scene.get("sprechertext")) for scene in scenes if _text(scene.get("sprechertext")))
        if spoken != _text(script.get("sprechertext")):
            errors.append("A06: Szenen-Sprechertext muss A05 wortgetreu und vollständig entsprechen; Disclaimer bleibt stumm.")
        _validate_scene_claims(scenes, script, errors)
        cta_spoken = " ".join(_text(scene.get("sprechertext")) for scene in scenes if _function(scene.get("funktion")) == "cta" and _text(scene.get("sprechertext")))
        cta = script.get("cta") if isinstance(script.get("cta"), Mapping) else {}
        if cta_spoken != _text(cta.get("text")):
            errors.append("A06: Der Abschnitt 48000–52000 ms muss genau den einen A05-CTA enthalten.")
        if _text(script.get("sprechertext")) not in _text(content.get("invideo_prompt")):
            errors.append("A06.invideo_prompt: Vollständiger wortgetreuer A05-Sprechertext fehlt im InVideo-Handoff.")


def _validate_qa(aid: str, content: Mapping[str, Any], production: bool, errors: list[str]) -> None:
    findings = _objects(content.get("findings"))
    checks = _objects(content.get("pflichtpruefungen"))
    _unique_ids(content.get("findings"), f"{aid}.inhalt.findings", errors)
    _unique_ids(content.get("pflichtpruefungen"), f"{aid}.inhalt.pflichtpruefungen", errors)
    identifiers = {check.get("id") for check in checks if isinstance(check.get("id"), str)}
    required = A07_REQUIRED_CHECKS if aid == "A07" else A10_REQUIRED_CHECKS
    missing = set(required) - identifiers
    if missing:
        errors.append(f"{aid}.pflichtpruefungen: Pflichtchecks fehlen: {', '.join(sorted(missing))}.")
    ready = content.get("ergebnis") == "freigabefaehig"
    blockers = [str(finding.get("id", "?")) for finding in findings if finding.get("offen") is True and finding.get("schwere") in {"K0", "K1"}]
    if ready and blockers:
        errors.append(f"{aid}: freigabefaehig widerspricht offenen K0/K1-Findings: {', '.join(blockers)}.")
    for check in checks:
        path = f"{aid}.Pflichtcheck {check.get('id', '?')}"
        if check.get("erledigt") is True and not _text(check.get("nachweis")):
            errors.append(f"{path}: Erledigte Prüfung benötigt einen konkreten Nachweis.")
        if production and check.get("erledigt") is True and _SIMULATION.search(_text(check.get("nachweis"))):
            errors.append(f"{path}: Simulations- oder Platzhalternachweis darf keine produktive Prüfung bestätigen.")
        if aid == "A07" and ready and check.get("id") in required:
            if check.get("anwendbar") is not True or check.get("erledigt") is not True:
                errors.append(f"{path}: Redaktionelle Freigabefähigkeit benötigt anwendbar=true und erledigt=true für jeden Pflichtcheck.")
    if aid == "A07" and content.get("freeze") is not None and not ready:
        errors.append("A07.freeze: Ein unvollständiges oder nacharbeitspflichtiges Artefakt darf keinen Freeze behaupten.")
    if aid == "A10":
        reports = _objects(content.get("technische_reports"))
        if ready and not reports:
            errors.append("A10: Technische Freigabefähigkeit benötigt tatsächliche technische Reports; ein leeres Prüfpaket ist keine Freigabe.")
        for i, report in enumerate(reports):
            _validate_technical_report(report, i, ready, errors)


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA_PATTERN.fullmatch(value) is not None


def _validate_technical_report(report: Mapping[str, Any], i: int, ready: bool, errors: list[str]) -> None:
    path = f"A10.technische_reports[{i}]"
    checks = _objects(report.get("checks"))
    resolutions = report.get("human_resolutions", {})
    if not isinstance(resolutions, Mapping):
        errors.append(f"{path}.human_resolutions: Menschliche Nachweise müssen als Objekt mit Prüfschlüssel vorliegen.")
        resolutions = {}
    valid_resolutions: set[str] = set()
    for key, proof in resolutions.items():
        if key not in MANUAL_TECHNICAL_CHECKS:
            errors.append(f"{path}.human_resolutions: Technischer Check {key!r} darf nicht manuell ersetzt werden.")
            continue
        if not isinstance(proof, Mapping) or not _text(proof.get("nachweis")) or not _valid_sha(proof.get("sha256")) or not _valid_sha(proof.get("attestation_sha256")):
            errors.append(f"{path}.human_resolutions.{key}: Konkreter Nachweispfad, dessen SHA-256 und attestation_sha256 sind Pflicht; keine Freigabesimulation.")
        else:
            valid_resolutions.add(key)
    if resolutions:
        original = report.get("urspruenglicher_report", report.get("ursprünglicher_report"))
        if not isinstance(original, Mapping) or not _text(original.get("path")) or not _valid_sha(original.get("sha256")):
            errors.append(f"{path}: Bei manuellen Ergänzungen muss der ursprüngliche technische Report mit Pfad und SHA-256 unverändert referenziert werden.")
    _unique_ids(report.get("checks"), path + ".checks", errors)
    for check in checks:
        if not _text(check.get("id")):
            errors.append(f"{path}.checks: Jeder technische Check benötigt eine konkrete ID.")
        if check.get("status") not in ("bestanden", "fehlgeschlagen", "nicht_geprueft"):
            errors.append(f"{path}.checks: Ungültiger technischer Status bei {check.get('id', '?')}.")
    if not ready:
        return
    if not _valid_sha(report.get("sha256")):
        errors.append(f"{path}: Freigabefähiger technischer Report benötigt den SHA-256 der tatsächlich geprüften Mediendatei.")
    malformed = not isinstance(report.get("checks"), list) or len(checks) != len(report.get("checks", []))
    if not checks or malformed:
        errors.append(f"{path}: Freigabefähiger Report benötigt tatsächliche strukturierte technische Checks.")
    unresolved = []
    for check in checks:
        key = check.get("id")
        status = check.get("status")
        if status == "bestanden":
            continue
        if status == "nicht_geprueft" and isinstance(key, str) and key in MANUAL_TECHNICAL_CHECKS and key in valid_resolutions and report.get("ergebnis") == "freigabefaehig":
            continue
        unresolved.append(str(key or "?"))
    if unresolved:
        errors.append(f"{path}: Fehlgeschlagene oder nicht geprüfte technische Checks widersprechen freigabefaehig: {', '.join(unresolved)}.")
    if report.get("ergebnis") not in ("bestanden", "freigabefaehig"):
        errors.append(f"{path}: Technischer Report bestätigt kein bestandenes oder nachweislich ergänztes Ergebnis.")


def _validate_render(content: Mapping[str, Any], index: Mapping[str, Any], production: bool, errors: list[str]) -> None:
    if production and content.get("render_real") is not True:
        errors.append("A08: Produktion benötigt einen echten Render; ein Prompt oder simulierter Render ist kein Preview.")
    qa = _content(index, "A07")
    if qa:
        if qa.get("ergebnis") != "freigabefaehig":
            errors.append("A08: Render darf nur auf einem redaktionell freigabefähigen A07 beruhen.")
        if not _text(qa.get("freeze")) or content.get("freeze") != qa.get("freeze"):
            errors.append("A08.freeze: Render muss an den konkreten A07-Freeze gebunden sein.")


def _validate_edit(content: Mapping[str, Any], production: bool, errors: list[str]) -> None:
    if production and content.get("musik_entfernt") is not True:
        if content.get("getrennte_spuren") is not True or not isinstance(content.get("ducking_db"), (int, float)) or isinstance(content.get("ducking_db"), bool):
            errors.append("A09: Verbleibende Musik benötigt getrennte Spuren und dokumentiertes Ducking; sonst Musik entfernen.")


def _validate_final_qa(content: Mapping[str, Any], index: Mapping[str, Any], errors: list[str]) -> None:
    preview = _content(index, "A08").get("preview")
    final = _content(index, "A09").get("final")
    if isinstance(preview, Mapping) and content.get("preview_sha256") != preview.get("sha256"):
        errors.append("A10.preview_sha256: Technische Prüfung referenziert eine andere Preview als A08.")
    if isinstance(final, Mapping) and content.get("final_sha256") is not None and content.get("final_sha256") != final.get("sha256"):
        errors.append("A10.final_sha256: Technische Prüfung referenziert eine andere Final-Datei als A09.")
    if content.get("ergebnis") == "freigabefaehig" and content.get("final_sha256") is None:
        errors.append("A10.final_sha256: Technische Freigabefähigkeit muss an die tatsächliche Final-Datei gebunden sein.")
    accepted_hashes = {content.get("preview_sha256"), content.get("final_sha256")} - {None}
    for i, report in enumerate(_objects(content.get("technische_reports"))):
        reported_hash = report.get("sha256")
        if reported_hash is not None and (not isinstance(reported_hash, str) or reported_hash not in accepted_hashes):
            errors.append(f"A10.technische_reports[{i}]: Report-SHA-256 gehört weder zur gebundenen Preview noch zur Final-Datei.")


def _validate_publication(content: Mapping[str, Any], data: Mapping[str, Any], index: Mapping[str, Any], production: bool, errors: list[str]) -> None:
    final = _content(index, "A09").get("final")
    qa = _content(index, "A10")
    if isinstance(final, Mapping) and content.get("final_sha256") != final.get("sha256"):
        errors.append("A11.final_sha256: Veröffentlichungsdatei stimmt nicht mit A09 überein.")
    if qa and content.get("final_sha256") != qa.get("final_sha256"):
        errors.append("A11.final_sha256: Veröffentlichung muss an die technisch geprüfte A10-Final-Datei gebunden sein.")
    public = content.get("visibility") == "oeffentlich" or data.get("status") == "veröffentlicht"
    if public:
        if content.get("visibility") != "oeffentlich":
            errors.append("A11: Status veröffentlicht benötigt visibility=oeffentlich.")
        for field in ("youtube_id", "url", "veroeffentlicht_am", "zielgruppe"):
            if not _text(content.get(field)):
                errors.append(f"A11.{field}: Öffentliche Veröffentlichung benötigt diese konkrete Angabe.")
        for field in ("ki_kennzeichnung", "werbung"):
            if not isinstance(content.get(field), bool):
                errors.append(f"A11.{field}: Vor Veröffentlichung ist eine tatsächliche Entscheidung erforderlich; null reicht nicht.")
        if not isinstance(content.get("playback_pruefung"), Mapping) or not content.get("playback_pruefung"):
            errors.append("A11.playback_pruefung: Öffentliche Veröffentlichung benötigt die tatsächliche Playback-Prüfung.")
    ai_used = any(asset.get("ki_illustration") is True for asset in _objects(_content(index, "A06").get("assets")))
    if ai_used and (production or public) and content.get("ki_kennzeichnung") is not True:
        errors.append("A11.ki_kennzeichnung: Verwendete KI-Illustrationen benötigen eine positive Kennzeichnungsentscheidung.")


def _validate_metrics(content: Mapping[str, Any], errors: list[str]) -> None:
    metrics = content.get("metriken")
    if isinstance(metrics, Mapping):
        for name, metric in metrics.items():
            if isinstance(metric, Mapping) and metric.get("wert") is None and not _text(metric.get("begruendung")):
                errors.append(f"A12.metriken.{name}: Nicht messbarer Wert bleibt null und benötigt eine konkrete Begründung; keine Zahl erfinden.")
    if content.get("regel_aenderung") is not False:
        errors.append("A12: Eine Beobachtungsrunde darf keine automatische Regeländerung auslösen.")
    if not isinstance(content.get("naechster_test"), str) or not _text(content.get("naechster_test")):
        errors.append("A12.naechster_test: Genau ein konkret beschriebener nächster Test ist erforderlich.")


def validate_artifact(data: Any, artifacts: Any = None, production: bool = False) -> list[str]:
    """Return German validation errors, without I/O to evidence or mutation.

    Structural draft validation permits a blocked draft with its stated reason.
    Production validation rejects blocked artifacts and DEMO artifacts. Optional
    ``artifacts`` supplies the actual dependencies for reference/hash checks;
    production validation requires that context for dependent artifacts.
    """
    if not isinstance(data, Mapping):
        return ["Artefakt muss ein JSON-Objekt sein."]
    aid = data.get("artefakt_id")
    if not isinstance(aid, str) or aid not in DEPENDENCIES:
        return ["artefakt_id: Pflichtfeld muss A01 bis A12 sein."]
    try:
        json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        return [f"{aid}: Artefakt ist kein gültiges JSON; nicht endliche Zahlen oder unzulässige Datentypen: {exc}."]
    errors = _nonstring_keys(data, aid)
    if errors:
        return _deduplicate(errors)
    try:
        schema_errors = sorted(_validators()[aid].iter_errors(data), key=lambda error: tuple(str(value) for value in error.absolute_path))
        errors.extend(_schema_message(aid, error) for error in schema_errors)
    except (OSError, ValueError) as exc:
        return [f"{aid}: Verbindliches JSON-Schema konnte nicht geladen werden: {exc}."]
    # Semantic checks operate only on a valid shape. This also prevents malformed
    # external JSON (for example a list in a status field) from raising an error
    # instead of returning a useful validation finding.
    if schema_errors:
        return _deduplicate(errors)
    contextual = artifacts is not None
    index, index_errors = _normalize_bundle(artifacts) if contextual else ({}, [])
    errors.extend(index_errors)
    if contextual and aid in index and index[aid] != data:
        errors.append(f"{aid}: Einzelartefakt stimmt nicht mit seiner Bundle-Version überein.")
    index[aid] = data
    _validate_common(data, index, contextual, production, errors)
    content = data.get("inhalt")
    if not isinstance(content, Mapping):
        return _deduplicate(errors)
    if aid == "A02":
        _validate_sources(content, production, errors)
    elif aid == "A03":
        _validate_claims(content, index, contextual, production, errors)
    elif aid == "A04":
        _validate_timeline(content, errors)
    elif aid == "A05":
        _validate_script(content, index, contextual, errors)
    elif aid == "A06":
        _validate_storyboard(content, data, index, contextual, production, errors)
    elif aid in {"A07", "A10"}:
        _validate_qa(aid, content, production, errors)
        if aid == "A10":
            _validate_final_qa(content, index, errors)
    elif aid == "A08":
        _validate_render(content, index, production, errors)
    elif aid == "A09":
        _validate_edit(content, production, errors)
    elif aid == "A11":
        _validate_publication(content, data, index, production, errors)
    elif aid == "A12":
        _validate_metrics(content, errors)
    return _deduplicate(errors)


def validate_bundle(artifacts: Any, production: bool = False) -> list[str]:
    """Validate an incremental bundle; require every declared dependency.

    An early bundle need not contain A01–A12 already. It must contain the full
    dependency chain of every included artifact, with matching project, version
    and canonical JSON SHA-256. Neither QA result nor this function records a
    gate approval or replaces expert/media checks.
    """
    index, errors = _normalize_bundle(artifacts)
    if not index and not errors:
        return ["Artefaktbundle ist leer."]
    projects = {artifact.get("projekt_id") for artifact in index.values() if isinstance(artifact.get("projekt_id"), str)}
    if len(projects) > 1:
        errors.append("Bundle: Artefakte aus unterschiedlichen Projekten dürfen nicht gemischt werden.")
    for aid in sorted(index):
        errors.extend(validate_artifact(index[aid], artifacts=index, production=production))
    return _deduplicate(errors)
