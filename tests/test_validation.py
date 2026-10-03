from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import unittest

import yaml

from medizinanders.validation import (
    A07_REQUIRED_CHECKS,
    A10_REQUIRED_CHECKS,
    DEPENDENCIES,
    TIMELINE,
    count_words,
    validate_artifact,
    validate_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
FINAL_SHA = "b" * 64
SRT_SHA = "c" * 64
DISCLAIMER = "Journalistischer Analyse-Content. Kein medizinischer Rat."
CLAIM_TEXT = "Im geprüften Original steht ein Stern aus Papier auf Seite eins."
SECTIONS = (
    ("Stell dir einen Stern aus Papier vor.",),
    ("Er liegt in einem Archiv und erzählt eine kleine Geschichte.",),
    (
        CLAIM_TEXT,
        "Lies diesen Satz in Ruhe und sieh genau auf die Wörter.",
        "Lass dabei Platz für Fragen und ziehe keine vorschnellen Schlüsse.",
        "Du kannst eine Quelle öffnen, ihre Stelle suchen und jeden Schritt nachvollziehen.",
        "Achte auf das Datum, den Zusammenhang und auf Grenzen der Aussage.",
        "So bleibt eine kurze Erzählung verständlich und die Prüfung für andere offen.",
    ),
    ("Ein Satz und ein Bild führen deinen Blick zurück zum klaren Ausgangspunkt.",),
    ("Schau dir jetzt die angegebene Originalquelle an.",),
    ("Lass dem kleinen Stern noch einen ruhigen Moment.",),
    (),
)


def digest(value):
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def statement(text, factual=False):
    return {"text": text, "faktisch": factual, "claim_ids": ["C001"] if factual else []}


def envelope(aid, content):
    return {
        "artefakt_id": aid,
        "projekt_id": "MA-20261003-001",
        "version": "1.0.0",
        "datum": "2026-10-03T12:00:00Z",
        "autor": "Unittest-Fixture",
        "status": "Entwurf",
        "eingaben": [],
        "quellen": [] if aid == "A01" else ["SRC001"],
        "offene_punkte": [],
        "gesperrt": False,
        "sperrgrund": None,
        "beispiel": False,
        "inhalt": content,
    }


def rebind(bundle):
    """Recompute hashes in dependency order after a deliberate fixture edit."""
    for aid in DEPENDENCIES:
        if aid in bundle:
            bundle[aid]["eingaben"] = [
                {"artefakt_id": dep, "version": bundle[dep]["version"], "sha256": digest(bundle[dep])}
                for dep in DEPENDENCIES[aid] if dep in bundle
            ]
    return bundle


def make_bundle():
    sentences = [
        {"id": f"S{i:02d}", **statement(text, text == CLAIM_TEXT), "funktion": function}
        for i, (function, text) in enumerate(
            ((function, text) for (function, _, _), texts in zip(TIMELINE, SECTIONS) for text in texts), 1
        )
    ]
    script = " ".join(sentence["text"] for sentence in sentences)
    content = {
        "A01": {
            "kernfrage": "Wie lässt sich ein kurzer Quellensatz prüfen?",
            "nutzen": "Eine nachvollziehbare Quellenprüfung zeigen.",
            "scope": ["Quellenlesen"], "ausschluesse": ["Medizinische Beratung"],
            "suchfragen": ["Was steht im Original?"], "format": "MA-SHORT-58-v1.0",
            "ressourcen": {"budget": 0}, "offene_entscheidungen": [],
        },
        "A02": {
            "sources": [{
                "id": "SRC001", "url": "https://example.org/original", "titel": "Originalquelle",
                "typ": "Originaldokument", "zugriff": "geprueft", "fundstelle": "Seite 1, Absatz 2",
                "abgerufen_am": "2026-10-03T11:00:00Z", "sha256": SHA,
                "original_geoeffnet": True, "lokaler_pfad": "sources/original.txt",
                "klinische_parameter": {key: None for key in (
                    "population", "design", "vergleich", "endpunkt", "absolute_wirkung", "relative_wirkung",
                    "unsicherheit", "interessenkonflikte", "grenzen",
                )},
            }],
            "suchprotokoll": ["Original geöffnet"], "gegenbelege": [], "korrekturen_retraktionen": [],
        },
        "A03": {
            "claims": [{
                "id": "C001", "text": CLAIM_TEXT, "status": "BESTÄTIGT", "einsatz": "ja",
                "source_ids": ["SRC001"], "fundstellen": ["Seite 1, Absatz 2"], "gegenbelege": [],
                "einschraenkungen": [], "risiken": [], "medizinisch_relevant": False,
                "rechtlich_relevant": False, "art": "quellenbehauptung",
            }],
            "faktenmatrix": [], "risikoübersicht": [], "psychologie_map": [],
            "medical_review_required": False, "legal_review_required": False,
        },
        "A04": {
            "profil": "MA-SHORT-58-v1.0",
            "abschnitte": [{"funktion": function, "start_ms": start, "ende_ms": end} for function, start, end in TIMELINE],
            "dramaturgie": "Quellenfrage, nachvollziehbare Prüfung und genau eine CTA.", "cta_anzahl": 1,
        },
        "A05": {
            "sprechertext": script, "wortzahl": count_words(script), "saetze": sentences,
            "untertitel_basis": script, "aussprache": [], "overlays": [],
            "titel": statement("Lies den Quellensatz"), "thumbnail": statement("Ein Stern aus Papier"),
            "beschreibung": statement(CLAIM_TEXT, True), "quellenangaben": ["SRC001, Seite 1, Absatz 2"],
            "cta": statement(SECTIONS[4][0]), "disclaimer": DISCLAIMER,
        },
        "A06": {
            "szenen": [{
                "id": f"SC{i:02d}", "start_ms": start, "ende_ms": end,
                "sprechertext": " ".join(texts), "funktion": function, "motiv": "Eigene Papiersterngrafik",
                "assets": ["AS001"], "sync_anker": f"{start} ms", "overlay": DISCLAIMER if start == 54000 else "",
                "quellenhinweis": "SRC001" if function == "Payload" else "",
                "uebergang": "harter Schnitt" if start == 3000 else "Schnitt",
                "audio": {"voiceover": bool(texts), "musik": False},
                "claim_ids": ["C001"] if function == "Payload" else [],
            } for i, ((function, start, end), texts) in enumerate(zip(TIMELINE, SECTIONS), 1)],
            "assets": [{
                "id": "AS001", "typ": "Eigene Grafik", "herkunft": "Eigenproduktion",
                "recht_status": "geklaert", "nachweis": "rights/grafik.pdf",
                "ki_illustration": False, "imitierte_stimme": False,
            }],
            "invideo_prompt": f"Profil MA-SHORT-58-v1.0; harter Schnitt bei 3 Sekunden; stiller Disclaimer 54–58 Sekunden. Sprechertext: {script}",
        },
        "A07": {
            "ergebnis": "freigabefaehig", "findings": [],
            "pflichtpruefungen": [{"id": key, "anwendbar": True, "erledigt": True, "nachweis": "Nachweis im geprüften Paket"} for key in A07_REQUIRED_CHECKS],
            "freeze": "FREEZE-001",
        },
        "A08": {
            "preview": {"path": "render/preview.mp4", "sha256": SHA}, "render_real": True,
            "operator": "Unittest-Operator", "render_zeitpunkt": "2026-10-03T13:00:00Z", "freeze": "FREEZE-001",
        },
        "A09": {
            "final": {"path": "render/final.mp4", "sha256": FINAL_SHA},
            "srt": {"path": "render/final.srt", "sha256": SRT_SHA}, "aenderungen": [],
            "musik_entfernt": True, "getrennte_spuren": True, "ducking_db": None,
        },
        "A10": {
            "technische_reports": [{"ergebnis": "bestanden", "sha256": FINAL_SHA, "checks": [
                {"id": "duration", "status": "bestanden", "ist": 58000, "soll": 58000, "grund": "Gemessen"},
            ]}],
            "findings": [], "pflichtpruefungen": [{"id": key, "anwendbar": True, "erledigt": False, "nachweis": ""} for key in A10_REQUIRED_CHECKS],
            "ergebnis": "freigabefaehig", "preview_sha256": SHA, "final_sha256": FINAL_SHA,
        },
        "A11": {
            "final_sha256": FINAL_SHA, "youtube_id": None, "url": None, "visibility": "vorbereitet",
            "ki_kennzeichnung": False, "zielgruppe": "Erwachsene", "werbung": False,
            "playback_pruefung": None, "veroeffentlicht_am": None,
        },
        "A12": {
            "datenquelle": "Messdaten noch nicht verfügbar", "zeitraum": "Erste sieben Tage nach Veröffentlichung",
            "metriken": {"aufrufe": {"wert": None, "begruendung": "Noch keine Veröffentlichung"}},
            "beobachtungen": [], "hypothesen": [], "naechster_test": "Genau einen anderen Einstieg testen.",
            "regel_aenderung": False,
        },
    }
    return rebind({aid: envelope(aid, value) for aid, value in content.items()})


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = make_bundle()

    def errors(self, aid, production=False, *, rehash=True):
        if rehash:
            rebind(self.bundle)
        return validate_artifact(self.bundle[aid], self.bundle, production=production)

    def assertError(self, errors, text):
        self.assertTrue(any(text in error for error in errors), f"{text!r} fehlt in {errors}")

    def test_valid_complete_bundle_with_human_checks_still_pending(self):
        self.assertEqual(validate_bundle(self.bundle), [])
        self.assertEqual(validate_bundle(self.bundle, production=True), [])
        # Artifact validation must not forge a human approval or mutate checks.
        self.assertFalse(self.bundle["A10"]["inhalt"]["pflichtpruefungen"][0]["erledigt"])

    def test_incremental_bundle_and_list_interface(self):
        early = {key: self.bundle[key] for key in ("A01", "A02", "A03")}
        self.assertEqual(validate_bundle(early), [])
        self.assertEqual(validate_bundle(list(early.values())), [])

    def test_no_mutation_and_repeatable_errors(self):
        self.bundle["A03"]["inhalt"]["claims"][0]["source_ids"] = ["unbekannt"]
        rebind(self.bundle)
        before = copy.deepcopy(self.bundle)
        first = validate_bundle(self.bundle)
        self.assertEqual(first, validate_bundle(self.bundle))
        self.assertEqual(self.bundle, before)

    def test_schema_and_templates_cover_all_twelve_artifacts(self):
        for aid in DEPENDENCIES:
            with self.subTest(aid=aid):
                schema = json.loads((ROOT / "schemas" / f"{aid}.schema.json").read_text())
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                template = yaml.safe_load((ROOT / "templates" / f"{aid}.yaml").read_text())
                self.assertEqual(template["artefakt_id"], aid)
                self.assertTrue(template["gesperrt"])
                self.assertEqual(template["status"], "Entwurf")
        source_template = yaml.safe_load((ROOT / "templates" / "A02.yaml").read_text())["inhalt"]["sources"][0]
        self.assertFalse(source_template["original_geoeffnet"])
        self.assertEqual(source_template["zugriff"], "nicht_geprueft")

    def test_required_envelope_and_content_fields(self):
        for field in ("autor", "version", "status", "gesperrt", "inhalt"):
            with self.subTest(field=field):
                artifact = copy.deepcopy(self.bundle["A01"])
                del artifact[field]
                self.assertError(validate_artifact(artifact), "Pflichtfeld")
        del self.bundle["A02"]["inhalt"]["sources"][0]["klinische_parameter"]["grenzen"]
        self.assertError(self.errors("A02"), "grenzen")

    def test_status_semver_and_iso_formats(self):
        for version in ("1", "v1.0.0", "01.0.0", "1.0.0-01"):
            with self.subTest(version=version):
                artifact = copy.deepcopy(self.bundle["A01"])
                artifact["version"] = version
                self.assertError(validate_artifact(artifact), "SemVer")
        artifact = copy.deepcopy(self.bundle["A01"])
        artifact["version"] = "1.2.3-rc.1+build.45"
        self.assertEqual(validate_artifact(artifact), [])
        artifact["status"] = "approved"
        self.assertError(validate_artifact(artifact), "Ungültiger Wert")
        artifact["status"] = "Entwurf"
        artifact["datum"] = "03.10.2026"
        self.assertTrue(validate_artifact(artifact))

    def test_empty_text_typos_and_invalid_project_date(self):
        self.bundle["A01"]["autor"] = "   "
        self.assertTrue(self.errors("A01"))
        self.bundle["A01"]["autor"] = "Autor"
        self.bundle["A01"]["inhalt"]["kernfrage_typo"] = "Typo"
        self.assertError(self.errors("A01"), "Unbekannte Felder")
        del self.bundle["A01"]["inhalt"]["kernfrage_typo"]
        self.bundle["A01"]["projekt_id"] = "MA-20260230-001"
        self.assertError(self.errors("A01"), "Datum in der Projekt-ID")

    def test_draft_blockade_and_production_blockade(self):
        artifact = self.bundle["A01"]
        artifact["gesperrt"] = True
        artifact["sperrgrund"] = "Originalprüfung fehlt"
        self.assertEqual(validate_artifact(artifact), [])
        self.assertError(validate_artifact(artifact, production=True), "gesperrt")
        artifact["status"] = "freigegeben"
        self.assertError(validate_artifact(artifact), "gesperrt")
        artifact["sperrgrund"] = None
        self.assertTrue(validate_artifact(artifact))

    def test_demo_and_open_points_are_not_production_evidence(self):
        artifact = self.bundle["A01"]
        artifact["beispiel"] = True
        self.assertEqual(validate_artifact(artifact), [])
        self.assertError(validate_artifact(artifact, production=True), "DEMO")
        artifact["beispiel"] = False
        artifact["offene_punkte"] = ["Scopeentscheidung fehlt"]
        self.assertError(validate_artifact(artifact, production=True), "Offene Punkte")

    def test_exact_dependency_ids_and_presence(self):
        self.bundle["A05"]["eingaben"].append(copy.deepcopy(self.bundle["A05"]["eingaben"][0]))
        self.assertError(self.errors("A05", rehash=False), "doppelt")
        self.bundle["A05"]["eingaben"].pop()
        self.bundle["A05"]["eingaben"] = self.bundle["A05"]["eingaben"][:1]
        self.assertError(self.errors("A05", rehash=False), "Pflichtabhängigkeiten")
        self.bundle["A05"]["eingaben"].append({"artefakt_id": "A01", "version": "1.0.0", "sha256": SHA})
        self.assertError(self.errors("A05", rehash=False), "Unzulässige Abhängigkeiten")
        self.assertError(validate_artifact(make_bundle()["A05"], production=True), "müssen die abhängigen")

    def test_stale_dependency_version_and_bytes(self):
        self.bundle["A04"]["version"] = "2.0.0"
        self.assertError(self.errors("A05", rehash=False), "Version von A04")
        self.assertError(self.errors("A05", rehash=False), "SHA-256 von A04")
        rebind(self.bundle)
        self.bundle["A04"]["inhalt"]["dramaturgie"] = "Nachträglich verändert"
        self.assertError(self.errors("A05", rehash=False), "SHA-256 von A04")

    def test_foreign_project_unknown_bundle_ids_and_missing_dependencies(self):
        self.bundle["A03"]["projekt_id"] = "MA-20261003-002"
        self.assertError(validate_bundle(self.bundle), "unterschiedlichen Projekten")
        self.assertError(validate_bundle({"A02": make_bundle()["A02"]}), "fehlt im Bundle")
        self.assertError(validate_bundle({"A99": make_bundle()["A01"]}), "Schlüssel passt")

    def test_unopened_and_inaccessible_original_cannot_confirm_claim(self):
        source = self.bundle["A02"]["inhalt"]["sources"][0]
        source["original_geoeffnet"] = False
        self.assertError(self.errors("A03"), "nicht am Original geprüft")
        self.assertError(self.errors("A02"), "Suchtreffer")
        source["original_geoeffnet"] = True
        source["zugriff"] = "nicht_geprueft"
        self.assertError(self.errors("A03"), "nicht am Original geprüft")
        source["zugriff"] = "geprueft"
        source["sha256"] = None
        self.assertError(self.errors("A03", production=True), "ohne lokalen Pfad und SHA-256")

    def test_unknown_sources_and_missing_claim_fundstelle(self):
        self.bundle["A03"]["inhalt"]["claims"][0]["source_ids"] = ["SRC-UNKNOWN"]
        self.assertError(self.errors("A03"), "Unbekannte Quellen-ID")
        self.bundle["A03"]["inhalt"]["claims"][0]["source_ids"] = ["SRC001"]
        self.bundle["A03"]["inhalt"]["claims"][0]["fundstellen"] = []
        self.assertError(self.errors("A03"), "konkrete Fundstellen")
        self.bundle["A05"]["quellen"] = ["SRC-UNKNOWN"]
        self.assertError(self.errors("A05"), "Unbekannte Quellen-ID")

    def test_ai_text_is_not_confirming_original_evidence(self):
        self.bundle["A02"]["inhalt"]["sources"][0]["typ"] = "KI-generierte Zusammenfassung"
        self.assertError(self.errors("A03"), "KI-generierte Quelle")

    def test_claim_status_usage_and_partial_limits(self):
        claim = self.bundle["A03"]["inhalt"]["claims"][0]
        for status in ("WIDERLEGT", "UNBEWIESEN", "TEILWEISE"):
            with self.subTest(status=status):
                claim["status"] = status
                self.assertTrue(self.errors("A03"))
                self.assertTrue(self.errors("A05"))
        claim["status"] = "TEILWEISE"
        claim["einsatz"] = "nur_mit_einschraenkung"
        self.assertError(self.errors("A03"), "ausdrückliche Einschränkungen")
        claim["einschraenkungen"] = ["nur in diesem Original"]
        self.assertError(self.errors("A05"), "Gesprochene Einschränkung")
        self.assertError(self.errors("A05"), "A05.beschreibung")

    def test_medical_need_cannot_be_hidden_by_false_flags_or_attribution(self):
        claim = self.bundle["A03"]["inhalt"]["claims"][0]
        for context in ("Metformin senkt den Blutzucker.", "Die Quelle behauptet eine Therapie gegen Krebs."):
            with self.subTest(context=context):
                claim["text"] = context
                self.assertError(self.errors("A03"), "medical_review_required=true")
        claim["text"] = CLAIM_TEXT
        claim["risiken"] = ["Dosierung könnte als Behandlungsrat verstanden werden"]
        self.assertError(self.errors("A03"), "medical_review_required=true")
        claim["risiken"] = []
        self.bundle["A03"]["inhalt"]["risikoübersicht"] = [{"problem": "Kontraindikation"}]
        self.assertError(self.errors("A03"), "medical_review_required=true")
        self.bundle["A03"]["inhalt"]["medical_review_required"] = True
        self.assertEqual(self.errors("A03"), [])

    def test_legal_need_detected_from_risks_and_explicit_flag(self):
        claim = self.bundle["A03"]["inhalt"]["claims"][0]
        claim["risiken"] = ["Werbliche Aussage und Datenschutz"]
        self.assertError(self.errors("A03"), "legal_review_required=true")
        claim["risiken"] = []
        claim["rechtlich_relevant"] = True
        self.assertError(self.errors("A03"), "legal_review_required=true")

    def test_factual_sentences_metadata_and_overlays_require_ids(self):
        for field in ("titel", "thumbnail", "beschreibung", "cta"):
            with self.subTest(field=field):
                bundle = make_bundle()
                bundle["A05"]["inhalt"][field] = {"text": CLAIM_TEXT, "faktisch": True, "claim_ids": []}
                rebind(bundle)
                self.assertError(validate_artifact(bundle["A05"], bundle), "benötigt mindestens eine Claim-ID")
        script = self.bundle["A05"]["inhalt"]
        script["saetze"][2]["claim_ids"] = []
        self.assertError(self.errors("A05"), "A05.saetze[2]")
        script["overlays"] = [{"text": CLAIM_TEXT, "faktisch": True, "claim_ids": [], "start_ms": 8000, "ende_ms": 12000}]
        self.assertError(self.errors("A05"), "A05.overlays[0]")

    def test_factual_flag_and_unknown_claim_references(self):
        script = self.bundle["A05"]["inhalt"]
        script["beschreibung"] = {"text": "Dieses Medikament heilt Krebs.", "faktisch": False, "claim_ids": []}
        self.assertError(self.errors("A05"), "Erkennbare Tatsachenbehauptung")
        script["beschreibung"] = {"text": CLAIM_TEXT, "faktisch": False, "claim_ids": []}
        self.assertError(self.errors("A05"), "Erkennbare Tatsachenbehauptung")
        script["beschreibung"] = {"text": "Fakt", "faktisch": True, "claim_ids": ["C999"]}
        self.assertError(self.errors("A05"), "Unbekannte Claim-ID")

    def test_missing_source_citations_for_used_claims(self):
        self.bundle["A05"]["inhalt"]["quellenangaben"] = []
        self.assertError(self.errors("A05"), "Quellenangaben für verwendete Claims")
        self.bundle["A05"]["inhalt"]["quellenangaben"] = ["https://example.org/original, Seite 1"]
        self.assertEqual(self.errors("A05"), [])

    def test_word_count_and_text_identity(self):
        script = self.bundle["A05"]["inhalt"]
        script["wortzahl"] += 1
        self.assertError(self.errors("A05"), "tatsächlich")
        script["wortzahl"] = count_words(script["sprechertext"])
        script["saetze"][0]["text"] += " Zusätzliche Wörter."
        self.assertError(self.errors("A05"), "nicht wortgetreu identisch")
        script["untertitel_basis"] = "Veränderter Text"
        self.assertError(self.errors("A05"), "Untertitelbasis")
        script["sprechertext"] = "Wort " * 99
        script["wortzahl"] = 100
        self.assertError(self.errors("A05"), "99 Wörter")
        script["sprechertext"] = "Wort " * 131
        script["wortzahl"] = 130
        self.assertError(self.errors("A05"), "131 Wörter")

    def test_word_counter_is_defined_for_unicode_compounds_and_decimals(self):
        self.assertEqual(count_words("Ärzte sagen: 1,5 mg, 3.2 ml – Arzt-Patienten-Gespräch und O’Connor."), 9)
        self.assertEqual(count_words("  ... — "), 0)

    def test_exactly_one_cta_in_script_and_timeline(self):
        script = self.bundle["A05"]["inhalt"]
        script["saetze"][0]["funktion"] = "CTA"
        self.assertError(self.errors("A05"), "Genau ein Satz")
        script["saetze"][0]["funktion"] = "Hook"
        script["saetze"][0]["text"] = "Abonniere unseren Kanal."
        self.assertError(self.errors("A05"), "Weitere erkennbare CTA")
        script["cta"]["text"] = "Eine andere CTA"
        self.assertError(self.errors("A05"), "identisch mit dem einzigen CTA")
        self.bundle["A04"]["inhalt"]["cta_anzahl"] = 2
        self.assertTrue(self.errors("A04"))

    def test_fixed_timeline_and_cross_section_scenes(self):
        self.bundle["A04"]["inhalt"]["abschnitte"][1]["ende_ms"] = 8100
        self.assertError(self.errors("A04"), "Open Loop muss exakt")
        scene = self.bundle["A06"]["inhalt"]["szenen"][1]
        scene["ende_ms"] = 8100
        self.assertError(self.errors("A06"), "keine Grenze")

    def test_scene_gaps_overlaps_wrong_functions_and_hard_cut(self):
        scene = self.bundle["A06"]["inhalt"]["szenen"][1]
        scene["start_ms"] = 3100
        self.assertError(self.errors("A06"), "Lücke, Überlappung")
        self.assertError(self.errors("A06"), "Hook-Schnitt")
        scene["start_ms"] = 3000
        scene["uebergang"] = "Weiche Blende"
        self.assertError(self.errors("A06"), "harten Schnitt")
        scene["uebergang"] = "harter Schnitt"
        scene["funktion"] = "Payload"
        self.assertError(self.errors("A06"), "Funktion muss")

    def test_disclaimer_is_silent_and_visible_for_full_end_interval(self):
        scene = self.bundle["A06"]["inhalt"]["szenen"][-1]
        for field in ("voiceover", "musik"):
            with self.subTest(field=field):
                scene["audio"][field] = True
                self.assertError(self.errors("A06"), "vollständig ohne")
                scene["audio"][field] = False
        scene["sprechertext"] = DISCLAIMER
        self.assertError(self.errors("A06"), "vollständig ohne")
        scene["sprechertext"] = ""
        scene["overlay"] = "Falscher Disclaimer"
        self.assertError(self.errors("A06"), "A05-Disclaimer")

    def test_disclaimer_cannot_be_inserted_in_script_or_covered(self):
        script = self.bundle["A05"]["inhalt"]
        script["sprechertext"] += " " + DISCLAIMER
        script["wortzahl"] = count_words(script["sprechertext"])
        self.assertError(self.errors("A05"), "ausschließlich eine stille Einblendung")
        script["overlays"] = [{**statement("Anderer Text"), "start_ms": 54000, "ende_ms": 58000}]
        self.assertError(self.errors("A05"), "ausschließlich der feste Disclaimer")

    def test_storyboard_preserves_script_and_factual_scene_ids(self):
        scene = self.bundle["A06"]["inhalt"]["szenen"][2]
        scene["claim_ids"] = []
        self.assertError(self.errors("A06"), "Claim-IDs für den faktischen Sprechertext")
        scene["sprechertext"] += " Veränderung."
        self.assertError(self.errors("A06"), "A05 wortgetreu")
        self.bundle["A06"]["inhalt"]["invideo_prompt"] = "Nur Stichworte"
        self.assertError(self.errors("A06"), "A05-Sprechertext fehlt")

    def test_storyboard_overlay_requires_typed_matching_statement(self):
        scene = self.bundle["A06"]["inhalt"]["szenen"][2]
        scene["overlay"] = "Originalquelle"
        self.assertError(self.errors("A06"), "zeitlich passendes A05-Statement")
        self.bundle["A05"]["inhalt"]["overlays"] = [{**statement("Originalquelle"), "start_ms": 8000, "ende_ms": 41000}]
        self.assertEqual(self.errors("A06"), [])

    def test_rights_and_asset_references(self):
        asset = self.bundle["A06"]["inhalt"]["assets"][0]
        asset["recht_status"] = "offen"
        self.assertEqual(self.errors("A06"), [])
        self.assertError(self.errors("A06", production=True), "Offene Assetrechte")
        asset["recht_status"] = "geklaert"
        asset["nachweis"] = ""
        self.assertError(self.errors("A06"), "konkreten Rechtebeleg")
        self.bundle["A06"]["inhalt"]["szenen"][0]["assets"] = ["AS-UNKNOWN"]
        self.assertError(self.errors("A06"), "Unbekannte Asset-ID")

    def test_imitation_always_blocks_even_with_written_consent(self):
        asset = self.bundle["A06"]["inhalt"]["assets"][0]
        asset["imitierte_stimme"] = True
        asset["nachweis"] = "Schriftliche Einwilligung zur Stimmkopie"
        self.assertError(self.errors("A06"), "Imitierte reale Stimmen sind verboten")
        asset["imitierte_stimme"] = False
        asset["typ"] = "Voice-clone einer realen Person"
        self.assertError(self.errors("A06"), "Imitierte reale Stimmen sind verboten")

    def test_ai_illustration_needs_explicit_and_visible_label(self):
        asset = self.bundle["A06"]["inhalt"]["assets"][0]
        asset["typ"] = "KI-Illustration"
        self.assertError(self.errors("A06"), "ki_illustration=true")
        asset["ki_illustration"] = True
        self.assertError(self.errors("A06"), "kennzeichnung")
        asset["kennzeichnung"] = "KI-Illustration"
        self.assertError(self.errors("A06"), "sichtbare Kennzeichnung")

    def test_qa_requires_named_checks_and_evidence(self):
        for aid in ("A07", "A10"):
            with self.subTest(aid=aid):
                content = self.bundle[aid]["inhalt"]
                content["pflichtpruefungen"][0]["id"] = "irrelevanter_check"
                self.assertError(self.errors(aid), "Pflichtchecks fehlen")
        qa = make_bundle()["A07"]
        qa["inhalt"]["pflichtpruefungen"][0]["nachweis"] = ""
        self.assertError(validate_artifact(qa), "konkreten Nachweis")

    def test_editorial_ready_cannot_skip_check_or_have_open_blocker(self):
        qa = self.bundle["A07"]["inhalt"]
        qa["pflichtpruefungen"][0]["erledigt"] = False
        self.assertError(self.errors("A07"), "anwendbar=true und erledigt=true")
        qa["pflichtpruefungen"][0]["erledigt"] = True
        for severity in ("K0", "K1"):
            qa["findings"] = [{"id": "F001", "datei": "A05", "problem": "Problem", "soll": "Ziel", "ist": "Ist", "schwere": severity, "rueckweg": "A05", "offen": True}]
            self.assertError(self.errors("A07"), "offenen K0/K1")
        qa["findings"][0]["schwere"] = "K2"
        self.assertEqual(self.errors("A07"), [])

    def test_incomplete_qa_does_not_claim_freeze_or_native_success(self):
        qa = self.bundle["A07"]["inhalt"]
        qa["ergebnis"] = "pruefung_unvollstaendig"
        self.assertError(self.errors("A07"), "keinen Freeze")
        qa["freeze"] = None
        self.assertEqual(self.errors("A07"), [])
        final_qa = self.bundle["A10"]["inhalt"]
        final_qa["ergebnis"] = "pruefung_unvollstaendig"
        final_qa["technische_reports"] = []
        final_qa["final_sha256"] = None
        self.assertEqual(self.errors("A10"), [])

    def test_native_qa_failure_and_missing_measurement_cannot_pass(self):
        qa = self.bundle["A10"]["inhalt"]
        qa["technische_reports"][0]["checks"][0]["status"] = "nicht_geprueft"
        self.assertError(self.errors("A10"), "nicht geprüfte technische Checks")
        qa["technische_reports"] = []
        self.assertError(self.errors("A10"), "tatsächliche technische Reports")
        qa["final_sha256"] = None
        self.assertError(self.errors("A10"), "tatsächliche Final-Datei")

    def test_manual_native_resolution_is_hash_bound_and_keeps_raw_unknown(self):
        report = self.bundle["A10"]["inhalt"]["technische_reports"][0]
        report["checks"].append({"id": "video_bitrate_target", "status": "nicht_geprueft", "ist": None, "soll": 10000000, "grund": "Encoder-Ziel nicht aus Datei messbar"})
        self.assertError(self.errors("A10"), "nicht geprüfte technische Checks")
        report.update({
            "ergebnis": "freigabefaehig",
            "human_resolutions": {"video_bitrate_target": {"nachweis": "reports/encoder.json", "sha256": SHA, "attestation_sha256": SRT_SHA}},
            "urspruenglicher_report": {"path": "reports/raw.json", "sha256": "d" * 64},
        })
        self.assertEqual(self.errors("A10"), [])
        self.assertEqual(report["checks"][-1]["status"], "nicht_geprueft")
        del report["human_resolutions"]["video_bitrate_target"]["attestation_sha256"]
        self.assertError(self.errors("A10"), "attestation_sha256")

    def test_manual_native_resolution_cannot_replace_failure_or_other_check(self):
        report = self.bundle["A10"]["inhalt"]["technische_reports"][0]
        proof = {"nachweis": "reports/encoder.json", "sha256": SHA, "attestation_sha256": SRT_SHA}
        report.update({"ergebnis": "freigabefaehig", "human_resolutions": {"video_bitrate_target": proof}, "urspruenglicher_report": {"path": "reports/raw.json", "sha256": "d" * 64}})
        report["checks"].append({"id": "video_bitrate_target", "status": "fehlgeschlagen", "ist": 0, "soll": 10000000, "grund": "Fehler"})
        self.assertError(self.errors("A10"), "Fehlgeschlagene")
        report["checks"][-1].update({"id": "video_codec", "status": "nicht_geprueft"})
        report["human_resolutions"] = {"video_codec": proof}
        self.assertError(self.errors("A10"), "darf nicht manuell ersetzt")

    def test_manual_native_resolution_requires_original_audit_report(self):
        report = self.bundle["A10"]["inhalt"]["technische_reports"][0]
        report["human_resolutions"] = {"audio_video_sync": {"nachweis": "reports/sync.txt", "sha256": SHA, "attestation_sha256": SRT_SHA}}
        self.assertError(self.errors("A10"), "ursprüngliche technische Report")
        report["sha256"] = [FINAL_SHA]
        self.assertTrue(self.errors("A10"))

    def test_partial_claim_limit_can_be_in_adjacent_annotated_sentence(self):
        claim = self.bundle["A03"]["inhalt"]["claims"][0]
        claim.update({"status": "TEILWEISE", "einsatz": "nur_mit_einschraenkung", "einschraenkungen": ["nur in diesem Original"]})
        script = self.bundle["A05"]["inhalt"]
        script["saetze"][3].update(statement("Diese Aussage gilt nur in diesem Original.", True))
        script["sprechertext"] = " ".join(sentence["text"] for sentence in script["saetze"])
        script["untertitel_basis"] = script["sprechertext"]
        script["wortzahl"] = count_words(script["sprechertext"])
        script["beschreibung"]["text"] += " Diese Aussage gilt nur in diesem Original."
        self.assertEqual(self.errors("A05"), [])
        script["beschreibung"]["text"] = CLAIM_TEXT
        self.assertError(self.errors("A05"), "A05.beschreibung: Einschränkung")

    def test_scene_subdivisions_preserve_fixed_sections_and_single_cta(self):
        scenes = self.bundle["A06"]["inhalt"]["szenen"]
        original = scenes[4]
        first, second = copy.deepcopy(original), copy.deepcopy(original)
        first.update({"id": "CTA-a", "ende_ms": 50000, "sprechertext": "Schau dir jetzt"})
        second.update({"id": "CTA-b", "start_ms": 50000, "sprechertext": "die angegebene Originalquelle an."})
        scenes[4:5] = [first, second]
        self.assertEqual(self.errors("A06"), [])

    def test_fixed_disclaimer_rejects_paraphrase(self):
        self.bundle["A05"]["inhalt"]["disclaimer"] = "Dies ist kein medizinischer Rat."
        self.assertError(self.errors("A05"), "Erwarteter fester Wert")

    def test_qa_finding_structure_and_simulated_evidence(self):
        self.bundle["A10"]["inhalt"]["findings"] = [{"id": "F001", "schwere": "K0", "offen": True}]
        self.assertError(self.errors("A10"), "Pflichtfeld")
        self.bundle["A07"]["inhalt"]["pflichtpruefungen"][0]["nachweis"] = "Simulation erfolgreich"
        self.assertError(self.errors("A07", production=True), "Simulations- oder Platzhalternachweis")

    def test_real_render_and_freeze_bindings(self):
        self.bundle["A08"]["inhalt"]["render_real"] = False
        self.assertError(self.errors("A08", production=True), "echten Render")
        self.bundle["A08"]["inhalt"]["freeze"] = "Falscher-Freeze"
        self.assertError(self.errors("A08"), "konkreten A07-Freeze")

    def test_music_must_be_removed_or_have_separate_ducked_tracks(self):
        edit = self.bundle["A09"]["inhalt"]
        edit["musik_entfernt"] = False
        self.assertError(self.errors("A09", production=True), "getrennte Spuren")
        edit["ducking_db"] = -18
        self.assertEqual(self.errors("A09", production=True), [])
        edit["getrennte_spuren"] = False
        self.assertError(self.errors("A09", production=True), "getrennte Spuren")

    def test_preview_final_reports_and_publication_hashes_match(self):
        self.bundle["A10"]["inhalt"]["preview_sha256"] = "d" * 64
        self.assertError(self.errors("A10"), "andere Preview")
        self.bundle["A10"]["inhalt"]["final_sha256"] = "e" * 64
        self.assertError(self.errors("A10"), "andere Final-Datei")
        self.bundle["A11"]["inhalt"]["final_sha256"] = "f" * 64
        self.assertError(self.errors("A11"), "Veröffentlichungsdatei")

    def test_publication_needs_decisions_and_actual_playback(self):
        publication = self.bundle["A11"]["inhalt"]
        publication["visibility"] = "oeffentlich"
        self.assertError(self.errors("A11"), "youtube_id")
        self.assertError(self.errors("A11"), "Playback-Prüfung")
        publication.update({"youtube_id": "abcdefghijk", "url": "https://youtube.com/watch?v=abcdefghijk", "veroeffentlicht_am": "2026-10-03T14:00:00Z", "playback_pruefung": {"ergebnis": "bestanden"}})
        self.assertEqual(self.errors("A11"), [])

    def test_ai_assets_require_publication_disclosure(self):
        self.bundle["A06"]["inhalt"]["assets"][0]["ki_illustration"] = True
        self.bundle["A06"]["inhalt"]["assets"][0]["kennzeichnung"] = "KI-Illustration"
        self.assertError(self.errors("A11", production=True), "Kennzeichnungsentscheidung")

    def test_null_metrics_need_reasons_and_only_one_next_test(self):
        metrics = self.bundle["A12"]["inhalt"]
        metrics["metriken"]["aufrufe"]["begruendung"] = None
        self.assertTrue(self.errors("A12"))
        metrics["metriken"]["aufrufe"] = {"wert": 0, "begruendung": None}
        self.assertEqual(self.errors("A12"), [])
        metrics["naechster_test"] = ["Test eins", "Test zwei"]
        self.assertError(self.errors("A12"), "Zeichenfolge")
        metrics["naechster_test"] = "Ein Test"
        metrics["regel_aenderung"] = True
        self.assertTrue(self.errors("A12"))

    def test_duplicate_local_ids_are_rejected(self):
        for aid, field in (("A02", "sources"), ("A03", "claims"), ("A05", "saetze"), ("A06", "assets"), ("A07", "pflichtpruefungen")):
            with self.subTest(aid=aid):
                bundle = make_bundle()
                bundle[aid]["inhalt"][field].append(copy.deepcopy(bundle[aid]["inhalt"][field][0]))
                rebind(bundle)
                self.assertError(validate_artifact(bundle[aid], bundle), "doppelt")

    def test_invalid_json_and_malformed_types_return_errors(self):
        for number in (math.nan, math.inf, -math.inf):
            artifact = copy.deepcopy(self.bundle["A01"])
            artifact["inhalt"]["ressourcen"]["budget"] = number
            self.assertError(validate_artifact(artifact), "kein gültiges JSON")
        malformed = copy.deepcopy(self.bundle["A03"])
        malformed["inhalt"]["claims"][0]["status"] = ["BESTÄTIGT"]
        self.assertTrue(validate_artifact(malformed))
        malformed = copy.deepcopy(self.bundle["A01"])
        malformed["inhalt"]["ressourcen"][1] = "kein JSON-Schlüssel"
        self.assertError(validate_artifact(malformed), "Objektschlüssel")
        self.assertTrue(validate_artifact(None))
        self.assertTrue(validate_bundle("kein Bundle"))
        self.assertTrue(validate_bundle([]))
        self.assertTrue(validate_bundle([self.bundle["A01"], self.bundle["A01"]]))


if __name__ == "__main__":
    unittest.main()
