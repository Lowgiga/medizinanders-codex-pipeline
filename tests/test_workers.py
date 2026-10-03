"""Native-worker boundary tests; subprocesses and confirmations stay mocked."""
from __future__ import annotations

import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from medizinanders.demo import (
    DEMO_OPERATOR, DEMO_TOPIC, _configure_demo, fixtures, prepare_sources,
)
from medizinanders.engine import Pipeline
from medizinanders.errors import PipelineError
from medizinanders.util import digest, load_json, write_json
from medizinanders.workers import (
    ROLE_INPUTS, ROLE_OUTPUTS, ROLE_PROMPTS, execute_worker,
    import_worker_result, prepare_worker,
)


REPO = Path(__file__).resolve().parents[1]


def confirm_in_test(prompt: str) -> str:
    phrases = [line.removeprefix("Eingabe: ") for line in prompt.splitlines()
               if line.startswith("Eingabe: ")]
    if len(phrases) != 1:
        raise AssertionError("Expected exactly one concrete test confirmation.")
    return phrases[0]


class WorkerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ma-worker-unittest-")
        self.addCleanup(self.temporary.cleanup)
        self.pipeline = Pipeline(Path(self.temporary.name) / "store", REPO)
        _configure_demo(self.pipeline)
        self.pipeline.approve_g0(DEMO_OPERATOR, confirm_in_test, simulation=True)
        self.pid = self.pipeline.new(DEMO_TOPIC, demo=True)
        self.root = self.pipeline.project(self.pid)
        prepare_sources(self.root)
        self.fixture = fixtures(self.pid)

    def import_ids(self, *ids):
        return self.pipeline.import_batch(self.pid, [copy.deepcopy(self.fixture[aid]) for aid in ids])

    def approve(self, gate):
        return self.pipeline.approve(gate, self.pid, DEMO_OPERATOR, confirm_in_test,
                                     simulation=True)

    def to_research(self):
        self.import_ids("A01")
        self.approve("G1")

    def to_beta(self):
        self.to_research()
        self.import_ids("A02", "A03")
        self.approve("G2")

    def result(self, workspace, *ids):
        task = load_json(workspace / "TASK.json")
        artifacts = [copy.deepcopy(self.fixture[aid]) for aid in ids]
        for artifact in artifacts:
            artifact["version"] = task["versions"].get(artifact["artefakt_id"], "0.1.0")
        path = workspace / "result.json"
        write_json(path, {"artifacts": artifacts})
        return path

    def test_each_worker_gets_one_role_and_fresh_minimal_context(self):
        first = prepare_worker(self.pipeline, self.pid, "GAMMA")
        second = prepare_worker(self.pipeline, self.pid, "GAMMA")
        self.assertNotEqual(first, second)
        self.assertEqual((first / "AGENTS.md").read_bytes(), (REPO / "agents/GAMMA.md").read_bytes())
        self.assertEqual({p.name for p in (first / "inputs").iterdir()}, {"brief.json", "channel.yaml"})
        self.assertEqual({p.name for p in (first / "schemas").iterdir()}, {"common.schema.json", "A01.schema.json"})
        self.assertFalse(list((first / "sources").iterdir()))
        self.assertTrue((first / "IMPLEMENTATION_CONTRACT.md").is_file())
        self.assertFalse((first / "state.json").exists())
        self.assertFalse((first / "operator.yaml").exists())
        task = load_json(first / "TASK.json")
        self.assertEqual(task["outputs"], ["A01"])
        self.assertEqual(task["input_binding"], {})
        self.assertEqual(task["versions"], {"A01": "0.1.0"})

    def test_research_worker_is_not_allowed_before_g1(self):
        self.import_ids("A01")
        with self.assertRaisesRegex(PipelineError, "G1"):
            prepare_worker(self.pipeline, self.pid, "RESEARCH")
        self.assertFalse((self.root / "workers/RESEARCH").exists())

    def test_beta_receives_only_a03_and_explicit_production_rules(self):
        self.to_beta()
        workspace = prepare_worker(self.pipeline, self.pid, "BETA")
        self.assertEqual({p.name for p in (workspace / "inputs").iterdir()},
                         {"A03.json", "channel.yaml", "production-rules.json"})
        task = load_json(workspace / "TASK.json")
        self.assertEqual(set(task["input_binding"]), {"A03"})
        self.assertEqual(task["outputs"], ["A04", "A05", "A06"])
        self.assertEqual(digest(workspace / "inputs/A03.json"), task["input_binding"]["A03"]["sha256"])
        production = load_json(workspace / "inputs/production-rules.json")
        self.assertEqual(set(production), {"stimme", "budget_eur", "invideo_moeglichkeiten", "G2_current"})
        self.assertFalse(list((workspace / "sources").iterdir()))
        self.assertEqual({p.name for p in (workspace / "schemas").iterdir()},
                         {"common.schema.json", "A04.schema.json", "A05.schema.json", "A06.schema.json"})

    def test_alpha_receives_only_registered_checked_originals(self):
        self.to_research()
        self.import_ids("A02")
        extra = self.root / "sources/unregistered-private.txt"
        extra.write_text("This unrelated source must not enter ALPHA.", encoding="utf-8")
        workspace = prepare_worker(self.pipeline, self.pid, "ALPHA")
        self.assertEqual({p.name for p in (workspace / "inputs").iterdir()}, {"A01.json", "A02.json"})
        self.assertEqual({p.name for p in (workspace / "sources").iterdir()}, {"demo_original.txt"})
        task = load_json(workspace / "TASK.json")
        for aid in ROLE_INPUTS["ALPHA"]:
            self.assertEqual(digest(workspace / "inputs" / f"{aid}.json"), task["input_binding"][aid]["sha256"])

    def test_sources_with_symlink_escape_are_rejected(self):
        self.to_research()
        external = Path(self.temporary.name) / "private-secret.txt"
        external.write_text("test-secret", encoding="utf-8")
        (self.root / "sources/escape.txt").symlink_to(external)
        with self.assertRaisesRegex(PipelineError, "Symlinks"):
            prepare_worker(self.pipeline, self.pid, "RESEARCH")

    def test_worker_result_cannot_supply_another_roles_artifacts(self):
        workspace = prepare_worker(self.pipeline, self.pid, "GAMMA")
        with self.assertRaisesRegex(PipelineError, "zugewiesenen Artefakte"):
            import_worker_result(self.pipeline, self.pid, self.result(workspace, "A02"))
        self.assertFalse(self.pipeline.state(self.pid)["current"])
        with self.assertRaisesRegex(PipelineError, "zugewiesenen Artefakte"):
            import_worker_result(self.pipeline, self.pid, self.result(workspace, "A01", "A01"))

    def test_extra_result_keys_and_non_worker_result_paths_are_rejected(self):
        workspace = prepare_worker(self.pipeline, self.pid, "GAMMA")
        path = self.result(workspace, "A01")
        result = load_json(path)
        result["approved"] = True
        write_json(path, result)
        with self.assertRaisesRegex(PipelineError, "exakt"):
            import_worker_result(self.pipeline, self.pid, path)
        outside = self.root / "untrusted/result.json"
        write_json(outside, {"artifacts": [self.fixture["A01"]]})
        with self.assertRaisesRegex(PipelineError, "isolierten Worker-Kontext"):
            import_worker_result(self.pipeline, self.pid, outside)

    def test_only_result_json_filename_is_importable(self):
        workspace = prepare_worker(self.pipeline, self.pid, "GAMMA")
        path = self.result(workspace, "A01")
        renamed = workspace / "other-output.json"
        path.rename(renamed)
        with self.assertRaises(PipelineError):
            import_worker_result(self.pipeline, self.pid, renamed)
        self.assertFalse(self.pipeline.state(self.pid)["current"])

    def test_non_object_artifact_is_a_domain_error_and_leaves_state_untouched(self):
        workspace = prepare_worker(self.pipeline, self.pid, "GAMMA")
        result = workspace / "result.json"
        write_json(result, {"artifacts": [42]})
        before = self.pipeline.state(self.pid)
        with self.assertRaises(PipelineError):
            import_worker_result(self.pipeline, self.pid, result)
        self.assertEqual(before, self.pipeline.state(self.pid))

    def test_incomplete_research_content_fails_before_any_source_copy(self):
        self.to_research()
        workspace = prepare_worker(self.pipeline, self.pid, "RESEARCH")
        result = self.result(workspace, "A02")
        data = load_json(result)
        data["artifacts"][0]["inhalt"] = {}
        write_json(result, data)
        before = self.pipeline.state(self.pid)
        originals = {str(path.relative_to(self.root)): digest(path)
                     for path in (self.root / "sources").rglob("*") if path.is_file()}
        with self.assertRaises(PipelineError):
            import_worker_result(self.pipeline, self.pid, result)
        self.assertEqual(before, self.pipeline.state(self.pid))
        self.assertEqual(originals, {str(path.relative_to(self.root)): digest(path)
                                    for path in (self.root / "sources").rglob("*") if path.is_file()})

    def test_changed_predecessor_rejects_prepared_result(self):
        self.to_research()
        workspace = prepare_worker(self.pipeline, self.pid, "RESEARCH")
        result = self.result(workspace, "A02")
        old_task = load_json(workspace / "TASK.json")
        revised = copy.deepcopy(self.pipeline.artifacts(self.pid)["A01"])
        revised.update(version=self.pipeline.output_version(self.pid, "A01"), status="Entwurf")
        revised["inhalt"]["kernfrage"] = "Updated topic after worker preparation"
        self.pipeline.import_batch(self.pid, [revised])
        self.assertNotEqual(old_task["input_binding"]["A01"], self.pipeline.state(self.pid)["current"]["A01"])
        with self.assertRaises(PipelineError):
            import_worker_result(self.pipeline, self.pid, result)
        self.assertNotIn("A02", self.pipeline.state(self.pid)["current"])

    def test_modified_input_copy_rejects_result_even_if_project_is_unchanged(self):
        self.to_research()
        workspace = prepare_worker(self.pipeline, self.pid, "RESEARCH")
        result = self.result(workspace, "A02")
        copied = workspace / "inputs/A01.json"
        data = load_json(copied)
        data["inhalt"]["kernfrage"] = "Tampered copied worker context"
        write_json(copied, data)
        with self.assertRaises(PipelineError):
            import_worker_result(self.pipeline, self.pid, result)
        self.assertNotIn("A02", self.pipeline.state(self.pid)["current"])

    def test_source_snapshot_hash_is_checked_before_copy_or_import(self):
        self.to_research()
        workspace = prepare_worker(self.pipeline, self.pid, "RESEARCH")
        result = self.result(workspace, "A02")
        (workspace / "sources/demo_original.txt").write_text("changed worker snapshot", encoding="utf-8")
        original_hash = digest(self.root / "sources/demo_original.txt")
        with self.assertRaises(PipelineError):
            import_worker_result(self.pipeline, self.pid, result)
        self.assertEqual(digest(self.root / "sources/demo_original.txt"), original_hash)
        self.assertNotIn("A02", self.pipeline.state(self.pid)["current"])

    def test_native_worker_has_no_inherited_secrets_and_never_autoapproves(self):
        observed = {}

        def native_fixture(command, **kwargs):
            observed.update(command=command, kwargs=kwargs)
            workspace = Path(kwargs["cwd"])
            self.result(workspace, "A01")
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-openai-secret",
                                     "GH_TOKEN": "unit-test-github-secret",
                                     "PRIVATE_BROWSER_TOKEN": "unit-test-browser-secret"}), \
             patch("medizinanders.workers.capabilities", return_value={"codex_exec": True}), \
             patch("medizinanders.workers.subprocess.run", side_effect=native_fixture) as run:
            workspace = execute_worker(self.pipeline, self.pid, "GAMMA")
        run.assert_called_once()
        command = observed["command"]
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn(str(workspace), command)
        environment = observed["kwargs"]["env"]
        secrets = {"OPENAI_API_KEY": "unit-test-openai-secret",
                   "GH_TOKEN": "unit-test-github-secret",
                   "PRIVATE_BROWSER_TOKEN": "unit-test-browser-secret"}
        for key, value in secrets.items():
            self.assertNotIn(key, environment)
            self.assertNotIn(value, observed["kwargs"]["input"])
        state = self.pipeline.state(self.pid)
        self.assertEqual(state["worker_starts"], 1)
        self.assertEqual(set(state["current"]), {"A01"})
        self.assertFalse(state["approvals"])
        self.assertEqual(self.pipeline.step(self.pid)["gate"], "G1")

    def test_authentication_failure_stops_once_and_leaves_prepared_context(self):
        def unauthorized(command, **kwargs):
            kwargs["stderr"].write("401 Unauthorized: synthetic unittest auth failure\n")
            return subprocess.CompletedProcess(command, 1)

        with patch("medizinanders.workers.capabilities", return_value={"codex_exec": True}), \
             patch("medizinanders.workers.subprocess.run", side_effect=unauthorized) as run:
            with self.assertRaisesRegex(PipelineError, "BLOCKED_AT: CODEX_RUNTIME"):
                execute_worker(self.pipeline, self.pid, "GAMMA")
        run.assert_called_once()
        workspaces = list((self.root / "workers/GAMMA").iterdir())
        self.assertEqual(len(workspaces), 1)
        workspace = workspaces[0]
        self.assertTrue((workspace / "START_HERE.md").is_file())
        self.assertIn("401 Unauthorized", (workspace / "native.stderr.log").read_text())
        self.assertFalse((workspace / "result.json").exists())
        state = self.pipeline.state(self.pid)
        self.assertEqual(state["worker_starts"], 1)
        self.assertFalse(state["current"])
        self.assertFalse(state["approvals"])

    def test_missing_native_runtime_prepares_context_without_launch(self):
        with patch("medizinanders.workers.capabilities", return_value={"codex_exec": False}), \
             patch("medizinanders.workers.subprocess.run") as run:
            with self.assertRaisesRegex(PipelineError, "CODEX_RUNTIME"):
                execute_worker(self.pipeline, self.pid, "GAMMA")
        run.assert_not_called()
        self.assertEqual(len(list((self.root / "workers/GAMMA").iterdir())), 1)
        self.assertEqual(self.pipeline.state(self.pid)["worker_starts"], 0)
        self.assertFalse(self.pipeline.state(self.pid)["approvals"])

    def test_prepare_only_has_no_runtime_or_authentication_side_effect(self):
        with patch("medizinanders.workers.capabilities") as capability, \
             patch("medizinanders.workers.subprocess.run") as run:
            workspace = execute_worker(self.pipeline, self.pid, "GAMMA", prepare_only=True)
        capability.assert_not_called()
        run.assert_not_called()
        self.assertTrue((workspace / "TASK.json").is_file())
        self.assertEqual(self.pipeline.state(self.pid)["worker_starts"], 0)

    def test_role_contract_lists_are_minimal_and_outputs_match_schemas(self):
        self.assertEqual(ROLE_INPUTS["BETA"], ["A03"])
        self.assertEqual(ROLE_INPUTS["QA_RED_TEAM"], [f"A{i:02}" for i in range(1, 7)])
        self.assertEqual(ROLE_OUTPUTS["BETA"], ["A04", "A05", "A06"])
        self.assertEqual(ROLE_OUTPUTS["QA_RED_TEAM"], ["A07"])
        for role, filename in ROLE_PROMPTS.items():
            self.assertTrue((REPO / "agents" / filename).is_file(), role)


if __name__ == "__main__":
    unittest.main()
