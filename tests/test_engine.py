"""Gate and media lifecycle regressions using private, disposable test stores.

The production branch is exercised only inside unittest. Media observations and
human confirmations below are explicitly simulated callbacks, never CLI approvals
or a claim that a test fixture was actually rendered, reviewed or published.
"""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from medizinanders.demo import (
    DEMO_OPERATOR, DEMO_TOPIC, ORIGINAL_PATH, _configure_demo, fixtures,
    prepare_sources,
)
from medizinanders.engine import HUMAN_CHECKS, Pipeline
from medizinanders.errors import PipelineError
from medizinanders.subtitles import generate_srt
from medizinanders.util import digest, load_json, write_json


REPO = Path(__file__).resolve().parents[1]
TEST_OPERATOR = "Unittest operator (simulation only)"


def confirm_in_test(prompt: str) -> str:
    """Simulate exactly the displayed phrase; do not use outside unit tests."""
    phrases = [line.removeprefix("Eingabe: ") for line in prompt.splitlines()
               if line.startswith("Eingabe: ")]
    if len(phrases) != 1:
        raise AssertionError("A concrete, unique confirmation phrase is required.")
    return phrases[0]


def simulated_video_report(path: Path, report_dir: Path) -> dict:
    """A mocked observation with real fixture-byte hashes and a raw test receipt."""
    report_dir.mkdir(parents=True, exist_ok=True)
    raw = report_dir / "unittest-observation.json"
    write_json(raw, {"test_only": True, "media_sha256": digest(path)})
    return {
        "sha256": digest(path), "ergebnis": "freigabefaehig",
        "checks": [{"id": "video_resolution", "status": "bestanden",
                    "ist": [1080, 1920], "soll": [1080, 1920],
                    "grund": "Mock observation inside unittest only."}],
        "raw_reports": [{"path": str(raw), "sha256": digest(raw)}],
    }


def simulated_subtitle_report(path: Path, font_path=None) -> dict:
    return {
        "sha256": digest(path), "ergebnis": "freigabefaehig",
        "checks": [{"id": "srt_format", "status": "bestanden",
                    "ist": "UTF-8 SRT fixture", "soll": "UTF-8 SRT",
                    "grund": "Mock observation inside unittest only."}],
    }


class FixtureMixin:
    production = False

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ma-engine-unittest-")
        self.addCleanup(self.temporary.cleanup)
        self.pipeline = Pipeline(Path(self.temporary.name) / "store", REPO)
        if self.production:
            config_path = self.pipeline.setup()
            config = self.pipeline.config()
            config.update({
                "verantwortliche_person": TEST_OPERATOR,
                "umgebung": "Disposable unittest environment; no real production",
                "invideo_moeglichkeiten": "Mocked unittest observation; no tool invocation",
                "zielgruppe": "Unit-test fixture", "stimme": "Unit-test voice choice",
                "budget_eur": 1, "zeitlimit_minuten": 10,
            })
            for key in ("datenschutz_bestaetigt", "rollenprompts_geprueft",
                        "speicherort_bestaetigt", "tools_geprueft",
                        "codex_nutzung_bestaetigt", "research_web_bestaetigt"):
                config[key] = True
            config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
            self.name = TEST_OPERATOR
        else:
            _configure_demo(self.pipeline)
            self.name = DEMO_OPERATOR
        self.pipeline.approve_g0(self.name, confirm_in_test, simulation=not self.production)
        self.new_case()

    def new_case(self):
        self.pid = self.pipeline.new(DEMO_TOPIC, demo=not self.production)
        self.root = self.pipeline.project(self.pid)
        prepare_sources(self.root)
        self.fixture = fixtures(self.pid)
        if self.production:
            # Only to exercise the production branch inside this isolated test.
            # Original contents still explicitly disclose their synthetic origin.
            for artifact in self.fixture.values():
                artifact["beispiel"] = False
                artifact["autor"] = "Unittest fixture; no real production"
            for check in self.fixture["A07"]["inhalt"]["pflichtpruefungen"]:
                check["nachweis"] = (
                    f"Unit-test assertion {check['id']} on the copied fixture bundle "
                    f"and original bytes in {ORIGINAL_PATH}."
                )

    def import_ids(self, *ids):
        return self.pipeline.import_batch(self.pid, [copy.deepcopy(self.fixture[aid]) for aid in ids])

    def approve(self, gate):
        return self.pipeline.approve(gate, self.pid, self.name, confirm_in_test,
                                     simulation=not self.production)

    def to_g1(self):
        self.import_ids("A01")
        self.approve("G1")

    def to_g2(self):
        self.to_g1()
        self.import_ids("A02", "A03")
        self.approve("G2")

    def to_g3(self):
        self.to_g2()
        self.import_ids("A04", "A05", "A06")
        self.import_ids("A07")
        freeze = self.pipeline.preflight(self.pid)
        self.approve("G3")
        return freeze


class EngineGateTests(FixtureMixin, unittest.TestCase):
    def test_home_inside_repository_is_rejected(self):
        with self.assertRaisesRegex(PipelineError, "außerhalb"):
            Pipeline(REPO / "private-test-store", REPO)

    def test_research_import_requires_actual_g1(self):
        self.import_ids("A01")
        before = self.pipeline.state(self.pid)
        self.assertEqual(self.pipeline.step(self.pid)["gate"], "G1")
        with self.assertRaisesRegex(PipelineError, "G1"):
            self.import_ids("A02")
        self.assertEqual(before, self.pipeline.state(self.pid))
        self.assertFalse((self.root / "artifacts/A02").exists())

    def test_demo_never_receives_a_productive_approval(self):
        self.import_ids("A01")
        with self.assertRaisesRegex(PipelineError, "strikt getrennt"):
            self.pipeline.approve("G1", self.pid, self.name, confirm_in_test)
        self.assertFalse(self.pipeline.state(self.pid)["approvals"])
        record = self.approve("G1")
        self.assertEqual(record["kind"], "DEMO_SIMULATION")
        self.assertTrue(self.pipeline.g0_valid(demo=True))
        self.assertFalse(self.pipeline.g0_valid(demo=False))

    def test_wrong_confirmation_preserves_draft_and_gate(self):
        self.import_ids("A01")
        before = self.pipeline.state(self.pid)
        draft = self.root / before["current"]["A01"]["path"]
        draft_hash = digest(draft)
        callback = Mock(return_value="yes")
        with self.assertRaisesRegex(PipelineError, "Keine Freigabe"):
            self.pipeline.approve("G1", self.pid, self.name, callback, simulation=True)
        callback.assert_called_once()
        self.assertIn("DEMO SIMULATION G1", callback.call_args.args[0])
        self.assertEqual(before, self.pipeline.state(self.pid))
        self.assertEqual(digest(draft), draft_hash)
        self.assertFalse((draft.parent / "v1.0.0.json").exists())

    def test_worker_cannot_import_approval_or_production_receipt(self):
        item = copy.deepcopy(self.fixture["A01"])
        item["status"] = "freigegeben"
        with self.assertRaisesRegex(PipelineError, "Worker dürfen keine"):
            self.pipeline.import_batch(self.pid, [item])
        item["status"] = "Entwurf"
        item["artefakt_id"] = "A08"
        with self.assertRaisesRegex(PipelineError, "ausschließlich vom Orchestrator"):
            self.pipeline.import_batch(self.pid, [item])
        self.assertFalse(self.pipeline.state(self.pid)["current"])

    def test_project_demo_flag_cannot_be_removed_during_import(self):
        item = copy.deepcopy(self.fixture["A01"])
        item["beispiel"] = False
        with self.assertRaisesRegex(PipelineError, "DEMO-Zuordnung"):
            self.pipeline.import_batch(self.pid, [item])

    def test_version_promotion_and_revision_leave_old_bytes_untouched(self):
        self.import_ids("A01")
        draft = self.root / "artifacts/A01/v0.1.0.json"
        draft_bytes = draft.read_bytes()
        self.approve("G1")
        released = self.root / "artifacts/A01/v1.0.0.json"
        released_bytes = released.read_bytes()
        revised = copy.deepcopy(self.pipeline.artifacts(self.pid)["A01"])
        revised["version"] = self.pipeline.output_version(self.pid, "A01")
        revised["status"] = "Entwurf"
        revised["inhalt"]["kernfrage"] = "Wie lässt sich die Quellenstelle genauer prüfen?"
        self.pipeline.import_batch(self.pid, [revised])
        self.assertEqual(draft.read_bytes(), draft_bytes)
        self.assertEqual(released.read_bytes(), released_bytes)
        self.assertEqual(self.pipeline.state(self.pid)["current"]["A01"]["version"], "1.1.0")
        self.assertFalse(self.pipeline.approval_valid(self.pid, "G1"))
        with self.assertRaisesRegex(PipelineError, "neue minor-Version"):
            self.pipeline.import_batch(self.pid, [revised])
        self.assertEqual(released.read_bytes(), released_bytes)

    def test_first_artifact_version_is_exactly_zero_one_zero(self):
        item = copy.deepcopy(self.fixture["A01"])
        item["version"] = "1.0.0"
        with self.assertRaisesRegex(PipelineError, "0.1.0"):
            self.pipeline.import_batch(self.pid, [item])

    def test_checked_source_requires_existing_snapshot_and_matching_hash(self):
        self.to_g1()
        for change in ("missing", "sha256", "original", "path"):
            with self.subTest(change=change):
                item = copy.deepcopy(self.fixture["A02"])
                source = item["inhalt"]["sources"][0]
                if change == "missing":
                    source["lokaler_pfad"] = "missing-original.txt"
                elif change == "sha256":
                    source["sha256"] = "0" * 64
                elif change == "original":
                    source["original_geoeffnet"] = False
                else:
                    source["lokaler_pfad"] = None
                before = self.pipeline.state(self.pid)
                with self.assertRaises(PipelineError):
                    self.pipeline.import_batch(self.pid, [item])
                self.assertEqual(before, self.pipeline.state(self.pid))
        self.import_ids("A02")
        self.assertIn("A02", self.pipeline.artifacts(self.pid))

    def test_direct_artifact_edits_are_detected_before_followup_work(self):
        self.to_g1()
        reference = self.pipeline.state(self.pid)["current"]["A01"]
        path = self.root / reference["path"]
        edited = load_json(path)
        edited["inhalt"]["kernfrage"] = "Unversioned external modification"
        write_json(path, edited)
        with self.assertRaisesRegex(PipelineError, "außerhalb der Versionierung"):
            self.pipeline.artifacts(self.pid)
        with self.assertRaises(PipelineError):
            self.pipeline.step(self.pid)

    def test_freeze_binds_a07_and_detects_modified_frozen_bytes(self):
        freeze = self.to_g3()
        self.assertEqual(self.pipeline.artifacts(self.pid)["A07"]["inhalt"]["freeze"], freeze)
        self.pipeline.verify_freeze(self.pid)
        frozen = self.root / "freeze" / freeze / "assets-rights.json"
        frozen.write_text("[]\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "Freeze-Hash"):
            self.pipeline.verify_freeze(self.pid)
        self.assertTrue(any("Freeze" in problem for problem in self.pipeline.gate_problems(self.pid, "G3")))

    def test_freeze_cannot_omit_a_required_binding_even_with_updated_manifest_hash(self):
        revision = self.to_g3()
        freeze = self.root / "freeze" / revision
        manifest_path = freeze / "manifest.json"
        manifest = load_json(manifest_path)
        manifest["artifact_binding"].pop("A03")
        write_json(manifest_path, manifest)
        sums = freeze / "SHA256SUMS"
        lines = [f"{digest(manifest_path)}  manifest.json" if line.endswith("  manifest.json") else line
                 for line in sums.read_text(encoding="utf-8").splitlines()]
        sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "Freeze-Pflichtbindungen"):
            self.pipeline.verify_freeze(self.pid)
        self.assertFalse(self.pipeline.approval_valid(self.pid, "G3"))

    def test_g3_requires_every_invideo_handoff_file(self):
        self.to_g2()
        self.import_ids("A04", "A05", "A06", "A07")
        self.pipeline.preflight(self.pid)
        missing = self.root / "handoff/invideo/VOICEOVER.txt"
        missing.unlink()
        callback = Mock(side_effect=confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "Pflicht-InVideo-Handoff.*VOICEOVER"):
            self.pipeline.approve("G3", self.pid, self.name, callback, simulation=True)
        callback.assert_not_called()
        self.assertNotIn("G3", self.pipeline.state(self.pid)["approvals"])

    def test_nonempty_modified_voiceover_cannot_bypass_beta_before_g3(self):
        self.to_g2()
        self.import_ids("A04", "A05", "A06", "A07")
        self.pipeline.preflight(self.pid)
        voiceover = self.root / "handoff/invideo/VOICEOVER.txt"
        voiceover.write_text(voiceover.read_text(encoding="utf-8") +
                             "\nUngeprüfte Ergänzung: Der Papierstern heilt jede Krankheit.\n",
                             encoding="utf-8")
        callback = Mock(side_effect=confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "[Hh]andoff"):
            self.pipeline.approve("G3", self.pid, self.name, callback, simulation=True)
        callback.assert_not_called()
        self.assertNotIn("G3", self.pipeline.state(self.pid)["approvals"])

    def test_invalidation_routes_preserve_earlier_gates_and_version_history(self):
        cases = {
            "source": ("A02", {"G1"}, "RESEARCH"),
            "meaning": ("A03", {"G1"}, "ALPHA"),
            "wording": ("A04", {"G1", "G2"}, "BETA"),
            "production": ("A06", {"G1", "G2"}, "BETA"),
            "export": ("A09", {"G1", "G2", "G3"}, None),
        }
        for index, (change, (removed, remaining, role)) in enumerate(cases.items()):
            with self.subTest(change=change):
                if index:
                    self.new_case()
                self.to_g3()
                before = self.pipeline.state(self.pid)
                historical = {ref["path"]: (self.root / ref["path"]).read_bytes()
                              for ref in before["current"].values()}
                next_step = self.pipeline.invalidate(self.pid, change, "Unit-test change route")
                after = self.pipeline.state(self.pid)
                self.assertEqual(set(after["approvals"]), remaining)
                self.assertNotIn(removed, after["current"])
                self.assertIn(removed, after["invalidations"][-1]["affected"])
                for file, payload in historical.items():
                    self.assertEqual((self.root / file).read_bytes(), payload)
                for gate in remaining:
                    self.assertTrue(self.pipeline.approval_valid(self.pid, gate))
                if role:
                    self.assertEqual(next_step.get("role"), role)
                else:
                    self.assertEqual(next_step.get("gate"), "G3_INVIDEO")

    def test_project_lock_excludes_an_independent_writer(self):
        other = Pipeline(self.pipeline.home, REPO)
        with self.pipeline.lock(self.pid):
            with self.assertRaisesRegex(PipelineError, "bereits bearbeitet"):
                with other.lock(self.pid):
                    self.fail("Concurrent writer acquired the project lock.")
        with other.lock(self.pid):
            self.assertTrue((self.root / ".lock").is_file())


class ProductionMediaLifecycleTests(FixtureMixin, unittest.TestCase):
    production = True

    def setUp(self):
        super().setUp()
        self.inspect_mock = patch("medizinanders.media.inspect_video", side_effect=simulated_video_report)
        self.subtitle_mock = patch("medizinanders.subtitles.validate_srt", side_effect=simulated_subtitle_report)
        self.inspect_mock.start()
        self.subtitle_mock.start()
        self.addCleanup(self.inspect_mock.stop)
        self.addCleanup(self.subtitle_mock.stop)

    def media_fixture(self, kind):
        path = self.root / "08_produktion/inbox" / f"{kind}.mp4"
        path.write_bytes(f"UNITTEST ONLY: {kind}, observations are mocked".encode())
        srt = self.root / "08_produktion/inbox/subtitles.srt"
        if not srt.exists():
            srt.write_text(generate_srt(self.fixture["A05"]["inhalt"], self.fixture["A06"]["inhalt"]), encoding="utf-8")
        return path

    def attestation(self, stage, **changes):
        template = (self.root / "handoff/playback/PLAYBACK_CHECKLIST.example.json"
                    if stage == "playback" else
                    self.root / "handoff/invideo" / f"{stage.upper()}_CHECKLIST.example.json")
        data = load_json(template)
        data.update({
            "example": False, "operator": self.name,
            "checked_at": "2026-01-01T12:00:00+00:00",
            "checks": {key: True for key in HUMAN_CHECKS},
            "notes": "Unit-test callback only; no real human or platform observation.",
            "technical_unknowns": {}, "evidence": {},
        })
        if stage == "preview":
            data["render_invideo"] = True
        if stage == "final":
            data["musik_entfernt"] = True
        if stage == "playback":
            data["checks"].update({
                key: True for key in ("playback_complete", "youtube_processing_complete",
                                     "metadata_exact", "audience_decided", "advertising_decided")
            })
        data.update(changes)
        path = self.root / f"unittest-{stage}-check.json"
        write_json(path, data)
        return path

    def to_g4(self):
        self.to_g3()
        self.pipeline.qa(self.pid, self.media_fixture("preview"), "preview")
        self.pipeline.attest(self.pid, "preview", self.attestation("preview"),
                             self.name, confirm_in_test)
        self.approve("G4")

    def write_decisions(self, **changes):
        path = self.root / "handoff/youtube/YOUTUBE_DECISIONS.json"
        data = load_json(path.with_name("YOUTUBE_DECISIONS.example.json"))
        data.update({
            "example": False, "operator": self.name,
            "ki_kennzeichnung": False, "zielgruppe": "Unit-test fixture", "werbung": False,
            "notes": "Explicit choices inside unittest only; no real upload.",
        })
        data.update(changes)
        write_json(path, data)
        return path

    def to_final_reviewed(self):
        self.to_g4()
        self.pipeline.qa(self.pid, self.media_fixture("final"), "final")
        self.pipeline.attest(self.pid, "final", self.attestation("final"),
                             self.name, confirm_in_test)
        self.write_decisions()

    def to_g5a(self):
        self.to_final_reviewed()
        self.approve("G5a")

    def to_reported_publication(self):
        self.to_g5a()
        private = self.pipeline.youtube_private(self.pid, "ABCDEFGHIJK", "https://youtu.be/ABCDEFGHIJK",
                                                self.name, confirm_in_test)
        self.pipeline.attest(self.pid, "playback", self.attestation("playback"),
                             self.name, confirm_in_test)
        self.approve("G5b")
        self.pipeline.youtube_published(self.pid, private["url"], self.name, confirm_in_test)
        return private

    def test_final_qa_and_human_attest_preserve_g4_and_require_explicit_g5a(self):
        self.to_g4()
        g4 = copy.deepcopy(self.pipeline.state(self.pid)["approvals"]["G4"])
        self.assertTrue(self.pipeline.attestation_valid(self.pid, "preview"))
        self.pipeline.qa(self.pid, self.media_fixture("final"), "final")
        state = self.pipeline.state(self.pid)
        self.assertEqual(state["approvals"]["G4"], g4)
        self.assertTrue(self.pipeline.approval_valid(self.pid, "G4"))
        self.assertTrue(self.pipeline.attestation_valid(self.pid, "preview"))
        self.assertNotIn("G5a", state["approvals"])
        artifacts = self.pipeline.artifacts(self.pid)
        self.assertEqual(artifacts["A10"]["inhalt"]["ergebnis"], "pruefung_unvollstaendig")
        self.assertFalse(artifacts["A09"]["inhalt"]["musik_entfernt"])
        before_attest_a09 = state["current"]["A09"]
        self.pipeline.attest(self.pid, "final", self.attestation("final"),
                             self.name, confirm_in_test)
        artifacts = self.pipeline.artifacts(self.pid)
        state = self.pipeline.state(self.pid)
        self.assertTrue(self.pipeline.approval_valid(self.pid, "G4"))
        self.assertTrue(self.pipeline.attestation_valid(self.pid, "final"))
        self.assertNotEqual(state["current"]["A09"], before_attest_a09)
        self.assertTrue((self.root / before_attest_a09["path"]).is_file())
        self.assertTrue(artifacts["A09"]["inhalt"]["musik_entfernt"])
        self.assertEqual(artifacts["A10"]["inhalt"]["ergebnis"], "freigabefaehig")
        technical = artifacts["A10"]["inhalt"]["technische_reports"][0]
        self.assertTrue(technical["checks"])
        self.assertEqual(technical["sha256"], artifacts["A09"]["inhalt"]["final"]["sha256"])
        self.assertNotIn("G5a", state["approvals"])
        with self.assertRaisesRegex(PipelineError, "YouTube-Entscheidungen"):
            self.approve("G5a")
        self.write_decisions()
        self.assertEqual(self.pipeline.gate_problems(self.pid, "G5a"), [])
        record = self.approve("G5a")
        self.assertEqual(record["kind"], "HUMAN_OPERATOR")
        self.assertTrue(self.pipeline.approval_valid(self.pid, "G5a"))
        self.assertFalse((self.root / "youtube-private.json").exists())

    def test_missing_human_check_prevents_final_gate(self):
        self.to_g4()
        self.pipeline.qa(self.pid, self.media_fixture("final"), "final")
        checks = {key: True for key in HUMAN_CHECKS}
        checks["subtitle_sync_100ms"] = False
        callback = Mock(side_effect=confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "manuellen Pflichtprüfungen"):
            self.pipeline.attest(self.pid, "final", self.attestation("final", checks=checks),
                                 self.name, callback)
        callback.assert_not_called()
        self.assertNotIn("final", self.pipeline.state(self.pid)["attestations"])
        with self.assertRaises(PipelineError):
            self.approve("G5a")
        self.assertNotIn("G5a", self.pipeline.state(self.pid)["approvals"])

    def test_technical_failure_cannot_be_overruled_by_all_human_checkboxes(self):
        self.to_g3()
        video = self.media_fixture("preview")

        def failed_observation(path, directory):
            report = simulated_video_report(path, directory)
            report["checks"][0].update(status="fehlgeschlagen", ist=[320, 568])
            report["ergebnis"] = "nacharbeit_erforderlich"
            return report

        with patch("medizinanders.media.inspect_video", side_effect=failed_observation):
            self.pipeline.qa(self.pid, video, "preview")
        self.pipeline.attest(self.pid, "preview", self.attestation("preview"),
                             self.name, confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "K1 video_resolution"):
            self.approve("G4")
        self.assertNotIn("G4", self.pipeline.state(self.pid)["approvals"])

    def test_mismatched_report_hash_is_rejected_before_receipt(self):
        self.to_g3()
        video = self.media_fixture("preview")
        with patch("medizinanders.media.inspect_video", return_value={
            "sha256": "0" * 64, "ergebnis": "freigabefaehig", "checks": [],
        }):
            with self.assertRaisesRegex(PipelineError, "während der Messung"):
                self.pipeline.qa(self.pid, video, "preview")
        self.assertNotIn("A08", self.pipeline.state(self.pid)["current"])

    def test_private_upload_requires_g5a_and_matching_actual_identifier(self):
        self.to_g3()
        with self.assertRaisesRegex(PipelineError, "G5a"):
            self.pipeline.youtube_private(self.pid, "ABCDEFGHIJK",
                                          "https://youtu.be/ABCDEFGHIJK", self.name, confirm_in_test)
        self.assertFalse((self.root / "youtube-private.json").exists())

    def test_export_change_preserves_preview_gate_and_revokes_final_gate(self):
        self.to_g5a()
        before = self.pipeline.state(self.pid)
        final_bytes = (self.root / before["current"]["A09"]["path"]).read_bytes()
        self.pipeline.invalidate(self.pid, "export", "Unit-test changed final export")
        after = self.pipeline.state(self.pid)
        self.assertNotIn("G5a", after["approvals"])
        self.assertNotIn("A09", after["current"])
        self.assertEqual((self.root / before["current"]["A09"]["path"]).read_bytes(), final_bytes)
        self.assertTrue(self.pipeline.approval_valid(self.pid, "G4"))
        self.assertTrue(self.pipeline.attestation_valid(self.pid, "preview"))
        self.assertIn("preview", after["reports"])

    def test_attest_rejects_a_different_media_hash_before_confirmation(self):
        self.to_g3()
        self.pipeline.qa(self.pid, self.media_fixture("preview"), "preview")
        before = copy.deepcopy(self.pipeline.state(self.pid)["current"]["A08"])
        callback = Mock(side_effect=confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "anderer Mediendatei"):
            self.pipeline.attest(self.pid, "preview",
                                 self.attestation("preview", preview_sha256="0" * 64),
                                 self.name, callback)
        callback.assert_not_called()
        self.assertEqual(self.pipeline.state(self.pid)["current"]["A08"], before)
        self.assertFalse(self.pipeline.artifacts(self.pid)["A08"]["inhalt"]["render_real"])

    def test_manual_resolution_binds_proof_and_keeps_raw_unknown_status(self):
        self.to_g4()

        def unmeasured_encoder_target(path, directory):
            report = simulated_video_report(path, directory)
            report["checks"].append({
                "id": "video_bitrate_target", "status": "nicht_geprueft",
                "ist": None, "soll": 10000000,
                "grund": "Encoder target needs an explicit settings receipt.",
            })
            report["ergebnis"] = "pruefung_unvollstaendig"
            return report

        with patch("medizinanders.media.inspect_video", side_effect=unmeasured_encoder_target):
            self.pipeline.qa(self.pid, self.media_fixture("final"), "final")
        evidence = self.root / "10_qa/unittest-encoder-settings.json"
        write_json(evidence, {"test_only": True, "bitrate_target_bps": 10000000})
        resolutions = {"video_bitrate_target": {
            "nachweis": str(evidence.relative_to(self.root)), "sha256": digest(evidence),
        }}
        self.pipeline.attest(self.pid, "final",
                             self.attestation("final", technical_unknowns=resolutions),
                             self.name, confirm_in_test)
        raw = self.pipeline.report(self.pid, "final")
        unknown = next(check for check in raw["checks"] if check["id"] == "video_bitrate_target")
        self.assertEqual(unknown["status"], "nicht_geprueft")
        qa = self.pipeline.artifacts(self.pid)["A10"]["inhalt"]
        self.assertEqual(qa["ergebnis"], "freigabefaehig")
        combined = qa["technische_reports"][0]
        self.assertEqual(combined["human_resolutions"]["video_bitrate_target"]["sha256"], digest(evidence))
        self.assertEqual(combined["human_resolutions"]["video_bitrate_target"]["attestation_sha256"],
                         self.pipeline.state(self.pid)["attestations"]["final"]["sha256"])
        self.write_decisions()
        self.assertEqual(self.pipeline.gate_problems(self.pid, "G5a"), [])
        evidence.write_text("changed test receipt\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "Nachweis.*Hash"):
            self.approve("G5a")
        self.assertNotIn("G5a", self.pipeline.state(self.pid)["approvals"])

    def test_playback_requires_completed_platform_processing(self):
        self.to_g5a()
        self.pipeline.youtube_private(self.pid, "ABCDEFGHIJK", "https://youtu.be/ABCDEFGHIJK",
                                      self.name, confirm_in_test)
        checklist = self.attestation("playback")
        data = load_json(checklist)
        data["checks"]["youtube_processing_complete"] = False
        write_json(checklist, data)
        callback = Mock(side_effect=confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "youtube_processing_complete"):
            self.pipeline.attest(self.pid, "playback", checklist, self.name, callback)
        callback.assert_not_called()
        with self.assertRaises(PipelineError):
            self.approve("G5b")
        self.assertNotIn("G5b", self.pipeline.state(self.pid)["approvals"])
        self.assertFalse((self.root / "youtube-published.json").exists())

    def test_full_operator_reported_workflow_reaches_publication_and_analytics(self):
        self.to_g5a()
        self.assertEqual(self.pipeline.step(self.pid)["gate"], "YOUTUBE_PRIVATE_UPLOAD")
        private = self.pipeline.youtube_private(self.pid, "ABCDEFGHIJK", "https://youtu.be/ABCDEFGHIJK",
                                                self.name, confirm_in_test)
        self.assertEqual(private["kind"], "HUMAN_REPORTED_NOT_API_VERIFIED")
        self.assertEqual(self.pipeline.step(self.pid)["gate"], "G5b")
        self.pipeline.attest(self.pid, "playback", self.attestation("playback"),
                             self.name, confirm_in_test)
        self.approve("G5b")
        self.assertFalse((self.root / "youtube-published.json").exists())
        self.assertEqual(self.pipeline.step(self.pid)["gate"], "YOUTUBE_PUBLICATION")
        self.pipeline.youtube_published(self.pid, private["url"], self.name, confirm_in_test)
        self.assertEqual(self.pipeline.artifacts(self.pid)["A11"]["status"], "veröffentlicht")
        self.assertEqual(self.pipeline.step(self.pid)["status"], "PUBLISHED_REPORTED_BY_HUMAN")
        analytics = self.root / "unittest-analytics.json"
        write_json(analytics, {
            "datenquelle": "Unittest fixture only; no platform query", "zeitraum": "2026-01-01/2026-01-02",
            "metriken": {"views": {"wert": 12, "begruendung": None}},
            "beobachtungen": ["Twelve views in the test fixture."],
            "hypothesen": ["A proposed explanation, not a measured causal effect."],
            "naechster_test": "Evaluate one alternate title in another isolated fixture.",
        })
        result = self.pipeline.analytics(self.pid, analytics)
        self.assertFalse(result["inhalt"]["regel_aenderung"])
        self.assertEqual(result["inhalt"]["metriken"]["views"]["wert"], 12)
        self.assertIsNone(result["inhalt"]["metriken"]["ctr"]["wert"])
        self.assertTrue(result["inhalt"]["metriken"]["ctr"]["begruendung"])
        self.assertEqual(self.pipeline.artifacts(self.pid)["A12"]["eingaben"][0]["artefakt_id"], "A11")

    def test_g5a_requires_every_youtube_handoff_file(self):
        self.to_final_reviewed()
        (self.root / "handoff/youtube/THUMBNAIL_BRIEF.md").unlink()
        callback = Mock(side_effect=confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "Pflicht-YouTube-Handoff.*THUMBNAIL"):
            self.pipeline.approve("G5a", self.pid, self.name, callback)
        callback.assert_not_called()
        self.assertNotIn("G5a", self.pipeline.state(self.pid)["approvals"])

    def test_upload_decisions_require_current_media_hashes_and_filled_template(self):
        self.to_final_reviewed()
        for key, value in (("final_sha256", "0" * 64),
                           ("srt_sha256", "0" * 64), ("example", True)):
            with self.subTest(key=key):
                self.write_decisions(**{key: value})
                callback = Mock(side_effect=confirm_in_test)
                with self.assertRaisesRegex(PipelineError, "aktuellen Final-/SRT-Hash"):
                    self.pipeline.approve("G5a", self.pid, self.name, callback)
                callback.assert_not_called()
                self.assertNotIn("G5a", self.pipeline.state(self.pid)["approvals"])
        self.write_decisions()
        self.approve("G5a")
        self.assertTrue(self.pipeline.approval_valid(self.pid, "G5a"))

    def test_changed_upload_decisions_invalidate_existing_g5a(self):
        self.to_g5a()
        decision = self.root / "handoff/youtube/YOUTUBE_DECISIONS.json"
        data = load_json(decision)
        data["zielgruppe"] = "A changed, unapproved test audience"
        write_json(decision, data)
        self.assertFalse(self.pipeline.approval_valid(self.pid, "G5a"))
        with self.assertRaisesRegex(PipelineError, "G5a"):
            self.pipeline.youtube_private(self.pid, "ABCDEFGHIJK", "https://youtu.be/ABCDEFGHIJK",
                                          self.name, confirm_in_test)
        self.assertFalse((self.root / "youtube-private.json").exists())

    def test_nonempty_modified_upload_title_cannot_add_claims_before_g5a(self):
        self.to_final_reviewed()
        title = self.root / "handoff/youtube/TITLE.txt"
        title.write_text("Der Papierstern heilt jede Krankheit.\n", encoding="utf-8")
        callback = Mock(side_effect=confirm_in_test)
        with self.assertRaisesRegex(PipelineError, "[Hh]andoff"):
            self.pipeline.approve("G5a", self.pid, self.name, callback)
        callback.assert_not_called()
        self.assertNotIn("G5a", self.pipeline.state(self.pid)["approvals"])

    def test_old_publication_marker_cannot_authorize_analytics_for_fresh_prepared_a11(self):
        self.to_reported_publication()
        marker = self.root / "youtube-published.json"
        old_marker = marker.read_bytes()
        publication = copy.deepcopy(self.pipeline.artifacts(self.pid)["A11"])
        publication["version"] = self.pipeline.output_version(self.pid, "A11")
        publication["status"] = "Entwurf"
        publication["inhalt"].update({
            "visibility": "vorbereitet", "youtube_id": None, "url": None,
            "playback_pruefung": None, "veroeffentlicht_am": None,
        })
        self.pipeline.import_batch(self.pid, [publication], internal=True)
        analytics = self.root / "unittest-stale-publication-analytics.json"
        write_json(analytics, {
            "datenquelle": "Unittest fixture only", "zeitraum": "2026-01-01/2026-01-02",
            "metriken": {"views": {"wert": 12, "begruendung": None}},
            "beobachtungen": [], "hypothesen": [], "naechster_test": "One fixture test",
        })
        before = self.pipeline.state(self.pid)
        with self.assertRaisesRegex(PipelineError, "Veröffentlichungsmarker.*veraltet"):
            self.pipeline.analytics(self.pid, analytics)
        self.assertEqual(before, self.pipeline.state(self.pid))
        self.assertEqual(marker.read_bytes(), old_marker)
        self.assertNotIn("A12", before["current"])

    def test_repeat_publication_archives_receipt_and_keeps_old_artifact_bytes(self):
        private = self.to_reported_publication()
        published = self.root / "youtube-published.json"
        old_receipt = published.read_bytes()
        old_a11 = self.pipeline.state(self.pid)["current"]["A11"]
        old_artifact_bytes = (self.root / old_a11["path"]).read_bytes()
        # A second report has fresh explicit confirmations on the current A11.
        self.approve("G5a")
        self.pipeline.attest(self.pid, "playback", self.attestation("playback"),
                             self.name, confirm_in_test)
        self.approve("G5b")
        self.pipeline.youtube_published(self.pid, private["url"], self.name, confirm_in_test)
        history = list((self.root / "youtube-history").glob("published-*.json"))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_bytes(), old_receipt)
        self.assertNotEqual(published.read_bytes(), old_receipt)
        self.assertEqual((self.root / old_a11["path"]).read_bytes(), old_artifact_bytes)
        self.assertNotEqual(self.pipeline.state(self.pid)["current"]["A11"], old_a11)


if __name__ == "__main__":
    unittest.main()
