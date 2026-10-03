from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from medizinanders.demo import (
    ASSET_PATH,
    CLAIM_ID,
    DISCLAIMER,
    ORIGINAL_BYTES,
    ORIGINAL_PATH,
    RIGHTS_PATH,
    SOURCE_ID,
    fixtures,
    prepare_sources,
    run_demo,
)
from medizinanders.errors import PipelineError
from medizinanders.util import digest, load_json


REPO = Path(__file__).resolve().parents[1]
PROJECT_ID = "MA-20261003-001"


class DemoFixtureTests(unittest.TestCase):
    def test_all_fixtures_are_fresh_synthetic_drafts(self):
        artifacts = fixtures(PROJECT_ID)
        self.assertEqual(set(artifacts), {f"A{index:02}" for index in range(1, 8)})
        for identifier, artifact in artifacts.items():
            self.assertEqual(artifact["artefakt_id"], identifier)
            self.assertEqual(artifact["projekt_id"], PROJECT_ID)
            self.assertTrue(artifact["beispiel"])
            self.assertEqual(artifact["status"], "Entwurf")
            self.assertEqual(artifact["eingaben"], [])
        artifacts["A03"]["inhalt"]["claims"][0]["status"] = "WIDERLEGT"
        self.assertEqual(fixtures(PROJECT_ID)["A03"]["inhalt"]["claims"][0]["status"], "BESTÄTIGT")

    def test_real_local_original_bytes_match_hash_and_fundstelle(self):
        source = fixtures(PROJECT_ID)["A02"]["inhalt"]["sources"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_sources(root)
            actual = (root / ORIGINAL_PATH).read_bytes()
            self.assertEqual(actual, ORIGINAL_BYTES)
            self.assertEqual(hashlib.sha256(actual).hexdigest(), source["sha256"])
            self.assertIn(source["fundstelle"].split(": ", 1)[1], actual.decode("utf-8"))
            self.assertIn("DEMO", actual.decode("utf-8"))
            self.assertEqual(source["lokaler_pfad"], Path(ORIGINAL_PATH).name)
            self.assertEqual(source["zugriff"], "geprueft")
            self.assertTrue(source["original_geoeffnet"])
            self.assertTrue(source["url"].startswith("https://example.invalid/DEMO/"))
            self.assertEqual(source["id"], SOURCE_ID)
            self.assertTrue((root / RIGHTS_PATH).is_file())
            self.assertIn(b">DEMO<", (root / ASSET_PATH).read_bytes())

    def test_existing_evidence_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_sources(root)
            prepare_sources(root)
            original = root / ORIGINAL_PATH
            original.write_text("Veränderter DEMO-Nachweis", encoding="utf-8")
            with self.assertRaisesRegex(PipelineError, "verändert"):
                prepare_sources(root)
            self.assertEqual(original.read_text(encoding="utf-8"), "Veränderter DEMO-Nachweis")

    def test_script_sentences_scenes_cta_and_disclaimer_are_exact(self):
        artifacts = fixtures(PROJECT_ID)
        script = artifacts["A05"]["inhalt"]
        scenes = artifacts["A06"]["inhalt"]["szenen"]
        self.assertEqual(script["sprechertext"], " ".join(row["text"] for row in script["saetze"]))
        self.assertEqual(script["sprechertext"], " ".join(row["sprechertext"] for row in scenes[:-1]))
        self.assertEqual(script["wortzahl"], len(script["sprechertext"].split()))
        self.assertGreaterEqual(script["wortzahl"], 100)
        self.assertLessEqual(script["wortzahl"], 130)
        self.assertNotIn(DISCLAIMER, script["sprechertext"])
        self.assertEqual(script["disclaimer"], DISCLAIMER)
        self.assertEqual(scenes[-1]["sprechertext"], "")
        self.assertEqual(scenes[-1]["overlay"], DISCLAIMER)
        self.assertFalse(scenes[-1]["audio"]["voiceover"])
        self.assertFalse(scenes[-1]["audio"]["musik"])
        self.assertEqual((scenes[-1]["start_ms"], scenes[-1]["ende_ms"]), (54000, 58000))
        self.assertEqual(script["sprechertext"].count(script["cta"]["text"]), 1)
        self.assertEqual([row["funktion"] for row in script["saetze"]].count("CTA"), 1)
        for scene in scenes:
            self.assertLessEqual(len(scene["sprechertext"]) / ((scene["ende_ms"] - scene["start_ms"]) / 1000), 18)

    def test_exact_profile_timeline(self):
        rows = fixtures(PROJECT_ID)["A04"]["inhalt"]["abschnitte"]
        self.assertEqual(
            [(row["funktion"], row["start_ms"], row["ende_ms"]) for row in rows],
            [
                ("Hook", 0, 3000),
                ("Open Loop", 3000, 8000),
                ("Payload", 8000, 41000),
                ("Verdichtung", 41000, 48000),
                ("CTA", 48000, 52000),
                ("Ausklang", 52000, 54000),
                ("Disclaimer", 54000, 58000),
            ],
        )

    def test_only_claim_is_about_the_fictional_source(self):
        artifacts = fixtures(PROJECT_ID)
        claim = artifacts["A03"]["inhalt"]["claims"][0]
        self.assertEqual(claim["id"], CLAIM_ID)
        self.assertEqual(claim["source_ids"], [SOURCE_ID])
        self.assertEqual(claim["art"], "quellenbehauptung")
        self.assertEqual(claim["status"], "BESTÄTIGT")
        self.assertEqual(claim["einsatz"], "ja")
        self.assertIn("fiktiven DEMO", claim["text"])
        self.assertFalse(claim["medizinisch_relevant"])
        self.assertFalse(claim["rechtlich_relevant"])
        self.assertTrue(claim["einschraenkungen"])
        script = artifacts["A05"]["inhalt"]
        statements = script["saetze"] + script["overlays"] + [script[key] for key in ("titel", "thumbnail", "beschreibung", "cta")]
        for statement in statements:
            self.assertEqual(statement["claim_ids"], [CLAIM_ID] if statement["faktisch"] else [])

    def test_all_required_preflight_checks_have_specific_demo_evidence(self):
        preflight = fixtures(PROJECT_ID)["A07"]["inhalt"]
        self.assertIsNone(preflight["freeze"])
        self.assertEqual(preflight["ergebnis"], "freigabefaehig")
        self.assertEqual(
            {row["id"] for row in preflight["pflichtpruefungen"]},
            {
                "claim_sentence_map", "sources_originals", "counterevidence_uncertainty",
                "medical_legal_escalation", "timeline_cta_disclaimer", "assets_rights",
                "invideo_complete",
            },
        )
        for row in preflight["pflichtpruefungen"]:
            self.assertTrue(row["anwendbar"])
            self.assertTrue(row["erledigt"])
            self.assertIn("DEMO-Fixture", row["nachweis"])


class DemoRunTests(unittest.TestCase):
    def _run(self, home: Path, *, with_video: bool = False):
        result = run_demo(home, REPO, with_video=with_video)
        self.addCleanup(shutil.rmtree, Path(result["snapshot_path"]))
        return result

    def test_complete_demo_exercises_actual_imports_gates_and_honest_stop(self):
        from medizinanders.engine import DEPENDENCIES, Pipeline
        from medizinanders.validation import validate_bundle

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original_operator = b"verantwortliche_person: PRODUCTION_UNTOUCHED\n"
            original_g0 = b'{"kind":"HUMAN_OPERATOR","untouched":true}\n'
            (home / "operator.yaml").write_bytes(original_operator)
            (home / "G0.json").write_bytes(original_g0)
            result = self._run(home)
            pid = result["projekt_id"]
            pipeline = Pipeline(home / "demo", REPO)
            project = pipeline.project(pid)
            state = pipeline.state(pid)
            artifacts = pipeline.artifacts(pid)

            self.assertEqual((home / "operator.yaml").read_bytes(), original_operator)
            self.assertEqual((home / "G0.json").read_bytes(), original_g0)
            self.assertFalse((home / "demo" / "G0.json").exists())
            self.assertEqual(load_json(home / "demo" / "G0.demo.json")["kind"], "DEMO_SIMULATION")
            self.assertTrue(state["demo"])
            self.assertEqual(result["typ"], "DEMO_SIMULATION")
            self.assertEqual(result["worker_roles"], ["GAMMA", "RESEARCH", "ALPHA", "BETA", "QA_RED_TEAM"])
            self.assertIn("G1", result["blocked_without_g1"])
            self.assertEqual(set(state["current"]), {f"A{index:02}" for index in range(1, 8)})
            self.assertEqual(set(state["approvals"]), {"G1", "G2", "G3"})
            self.assertEqual(result["simulated_gates"], ["G0", "G1", "G2", "G3"])
            self.assertEqual(set(result["blocked_media_gates"]), {"G4", "G5a", "G5b"})
            self.assertEqual(validate_bundle(artifacts, production=False), [])
            for identifier, artifact in artifacts.items():
                self.assertTrue(artifact["beispiel"])
                self.assertEqual(artifact["version"], "1.0.0")
                self.assertEqual({entry["artefakt_id"] for entry in artifact["eingaben"]}, set(DEPENDENCIES[identifier]))
                for entry in artifact["eingaben"]:
                    binding = state["current"][entry["artefakt_id"]]
                    self.assertEqual(entry["sha256"], binding["sha256"])
                    self.assertEqual(entry["version"], binding["version"])
                draft = load_json(project / "artifacts" / identifier / "v0.1.0.json")
                self.assertEqual(draft["status"], "Entwurf")
                self.assertTrue(draft["beispiel"])
            for reference in state["approvals"].values():
                self.assertEqual(load_json(project / reference["path"])["kind"], "DEMO_SIMULATION")
            pipeline.verify_freeze(pid)
            self.assertEqual(state["freeze"], result["freeze"])
            self.assertEqual(state["reviews"], {})
            self.assertEqual(state["attestations"], {})
            self.assertEqual(state["worker_starts"], 0)
            for role in result["worker_roles"]:
                worker_result = load_json(project / "workers" / "DEMO" / role / "result.json")
                self.assertTrue(all(artifact["beispiel"] for artifact in worker_result["artifacts"]))
            handoff = project / "handoff" / "invideo"
            for name in (
                "INVIDEO_PROMPT.txt", "VOICEOVER.txt", "SUBTITLE_BASE.txt", "SCENE_PLAN.md",
                "ASSET_MANIFEST.yaml", "RIGHTS_CHECKLIST.md", "EXPECTED_OUTPUT.md",
                "OPERATOR_STEPS.md", "DEMO_ESTIMATED.srt",
            ):
                self.assertTrue((handoff / name).is_file(), name)
            for stage in ("PREVIEW", "FINAL"):
                checklist = load_json(handoff / f"{stage}_CHECKLIST.example.json")
                self.assertTrue(all(value is False for value in checklist["checks"].values()))
            self.assertFalse(any(check["status"] == "fehlgeschlagen" for check in result["subtitles"]["checks"]))
            self.assertTrue(any(check["status"] == "nicht_geprueft" for check in result["subtitles"]["checks"]))
            self.assertEqual(result["next"]["status"], "WAITING_FOR_HUMAN")
            self.assertEqual(result["next"]["gate"], "G3_INVIDEO")
            self.assertFalse(result["published"])
            self.assertEqual(result["production_approvals"], 0)
            self.assertIsNone(result["media"])
            self.assertFalse((project / "youtube-private.json").exists())
            self.assertFalse((project / "youtube-published.json").exists())
            with self.assertRaisesRegex(PipelineError, "strikt getrennt"):
                pipeline.approve("G1", pid, "Fiktive Person", lambda prompt: "", simulation=False)
            snapshot = Path(result["snapshot_path"])
            report = Path(result["report_path"]).read_text(encoding="utf-8")
            self.assertIn("| 13 | Ehrlicher Stopp |", report)
            self.assertIn("DEMO_SIMULATION", report)
            self.assertIn("keinen echten InVideo-Render", report)
            self.assertEqual(digest(snapshot / ORIGINAL_PATH), artifacts["A02"]["inhalt"]["sources"][0]["sha256"])
            sanitized = (snapshot / "DEMO_RESULT.json").read_text(encoding="utf-8")
            self.assertNotIn(directory, sanitized)
            self.assertIn("<DEMO_PROJECT>", sanitized)
            self.assertFalse(json.loads(sanitized)["published"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "echtes ffmpeg/ffprobe für Negativtest fehlt")
    def test_real_wrong_size_demo_video_fails_qa_without_media_approval(self):
        from medizinanders.engine import Pipeline

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self._run(home, with_video=True)
            pipeline = Pipeline(home / "demo", REPO)
            pid = result["projekt_id"]
            state = pipeline.state(pid)
            preview = pipeline.artifacts(pid)["A08"]
            checks = {check["id"]: check for check in result["media"]["checks"]}
            self.assertEqual(result["media"]["ergebnis"], "nacharbeit_erforderlich")
            self.assertEqual(checks["video_resolution"]["status"], "fehlgeschlagen")
            self.assertEqual(checks["duration"]["status"], "bestanden")
            self.assertEqual(checks["video_frame_count"]["status"], "bestanden")
            self.assertEqual(preview["inhalt"]["preview"]["sha256"], result["media"]["sha256"])
            self.assertTrue(preview["beispiel"])
            self.assertFalse(preview["inhalt"]["render_real"])
            self.assertEqual(result["next"]["gate"], "G4")
            self.assertEqual(set(state["approvals"]), {"G1", "G2", "G3"})
            self.assertEqual(state["attestations"], {})
            self.assertFalse(result["published"])
            self.assertFalse(any(identifier in state["current"] for identifier in ("A09", "A10", "A11", "A12")))
            video_path = pipeline.project(pid) / preview["inhalt"]["preview"]["path"]
            self.assertEqual(digest(video_path), result["media"]["sha256"])
            self.assertTrue((Path(result["snapshot_path"]) / preview["inhalt"]["preview"]["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
