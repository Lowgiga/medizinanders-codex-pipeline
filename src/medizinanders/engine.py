from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

import yaml

from .errors import PipelineError
from .util import canonical, contained, digest, load_json, next_version, now, object_hash, project_id, write_json


DEPENDENCIES = {
    "A01": [], "A02": ["A01"], "A03": ["A01", "A02"],
    "A04": ["A03"], "A05": ["A03", "A04"], "A06": ["A03", "A04", "A05"],
    "A07": ["A01", "A02", "A03", "A04", "A05", "A06"], "A08": ["A07"],
    "A09": ["A05", "A06", "A08"], "A10": ["A07", "A08", "A09"],
    "A11": ["A05", "A10"], "A12": ["A11"],
}
GATE_ARTIFACTS = {
    "G1": ["A01"], "G2": ["A01", "A02", "A03"],
    "G3": [f"A{i:02}" for i in range(1, 8)],
    "G4": [f"A{i:02}" for i in range(1, 9)],
    "G5a": [f"A{i:02}" for i in range(1, 12)],
    "G5b": [f"A{i:02}" for i in range(1, 12)],
}
GATES = ["G1", "G2", "G3", "G4", "G5a", "G5b"]
HUMAN_CHECKS = [
    "voiceover_exact", "pronunciation", "subtitle_sync_100ms", "subtitle_visual",
    "font_layout", "burned_subtitles", "smartphone_listening", "disclaimer_visual",
    "rights", "ai_label", "patient_privacy", "audio_music_verified",
]
PLAYBACK_CHECKS = ["playback_complete", "youtube_processing_complete", "metadata_exact", "audience_decided", "advertising_decided"]
INVIDEO_FILES = ["INVIDEO_PROMPT.txt", "SCENE_PLAN.md", "VOICEOVER.txt", "SUBTITLE_BASE.txt", "ASSET_MANIFEST.yaml",
                 "RIGHTS_CHECKLIST.md", "EXPECTED_OUTPUT.md", "OPERATOR_STEPS.md"]
YOUTUBE_FILES = ["YOUTUBE_HANDOFF.md", "TITLE.txt", "DESCRIPTION.txt", "TAGS.txt", "THUMBNAIL_BRIEF.md", "SOURCE_LINKS.md",
                 "UPLOAD_MANIFEST.json", "subtitles.srt"]
GATE_MEANING = {
    "G0": "Betrieb: Verantwortung, Datenschutz, Rollen, Speicher, Werkzeuge, tatsächliches InVideo und Kostenrahmen.",
    "G1": "Genau diesen Themenauftrag, Scope, offene Entscheidungen und Rechercheaufwand freigeben.",
    "G2": "Genau diese Claims, Originalquellen, Gegenbelege, Einschränkungen und Risiken inhaltlich freigeben.",
    "G3": "Genau dieses Freeze-Paket für EINEN manuell gestarteten InVideo-Entwurf freigeben; Kosten selbst prüfen.",
    "G4": "Genau diese tatsächlich gerenderte Vorschau nach technischer, visueller und Hörprüfung freigeben.",
    "G5a": "Genau diese Finaldatei mit SHA-256 ausschließlich für PRIVATEN manuellen Upload freigeben.",
    "G5b": "Genau dieses verarbeitete private YouTube-Video nach echter Wiedergabeprüfung zur manuellen Veröffentlichung freigeben.",
}


class Pipeline:
    """Der einzige Schreiber für State, Versionen, Freigaben und deren Rückwege."""

    def __init__(self, home: Path, repo: Path):
        self.home, self.repo = Path(home).expanduser().resolve(), Path(repo).resolve()
        if self.home.is_relative_to(self.repo):
            raise PipelineError("MA_HOME muss außerhalb des Git-Repositories liegen (z. B. ~/.local/share/medizinanders).")

    @contextmanager
    def lock(self, pid: str | None = None):
        root = self.home if pid is None else self.project(pid)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (root / ".lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise PipelineError("Dieses Projekt wird bereits bearbeitet. Den laufenden Vorgang zuerst beenden.") from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def project(self, pid: str) -> Path:
        return self.home / "projects" / project_id(pid)

    def setup(self) -> Path:
        with self.lock():
            path = self.home / "operator.yaml"
            if not path.exists():
                shutil.copyfile(self.repo / "config/operator.example.yaml", path)
                os.chmod(path, 0o600)
            self.home.chmod(0o700)
            return path

    def config(self) -> dict:
        path = self.home / "operator.yaml"
        if not path.is_file():
            raise PipelineError("Betrieb noch nicht eingerichtet. Zuerst: ma setup")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PipelineError(f"operator.yaml ist ungültig: {exc}") from exc
        if not isinstance(data, dict):
            raise PipelineError("operator.yaml muss ein YAML-Objekt enthalten.")
        return data

    def rules_hash(self) -> str:
        files = [self.repo / "config/channel.yaml", self.repo / "IMPLEMENTATION_CONTRACT.md"]
        for folder, suffix in [("agents", ".md"), ("schemas", ".json"), ("src/medizinanders", ".py")]:
            files += sorted((self.repo / folder).glob("*" + suffix))
        return object_hash({str(p.relative_to(self.repo)): digest(p) for p in files})

    def operating_binding(self) -> dict:
        return {"rules_sha256": self.rules_hash(), "operator_sha256": digest(self.home / "operator.yaml")}

    def g0_valid(self, demo: bool = False) -> bool:
        path = self.home / ("G0.demo.json" if demo else "G0.json")
        if not path.is_file():
            return False
        record = load_json(path)
        return (record.get("binding") == self.operating_binding()
                and record.get("kind") == ("DEMO_SIMULATION" if demo else "HUMAN_OPERATOR")
                and bool(record.get("name")))

    def approve_g0(self, name: str, confirmation: Callable[[str], str], simulation: bool = False) -> dict:
        with self.lock():
            cfg = self.config()
            required = ["verantwortliche_person", "umgebung", "invideo_moeglichkeiten", "zielgruppe", "stimme"]
            missing = [key for key in required if not isinstance(cfg.get(key), str) or not cfg[key].strip()]
            for key in ["datenschutz_bestaetigt", "rollenprompts_geprueft", "speicherort_bestaetigt",
                        "tools_geprueft", "codex_nutzung_bestaetigt", "research_web_bestaetigt"]:
                if cfg.get(key) is not True:
                    missing.append(key)
            for key in ["budget_eur", "zeitlimit_minuten"]:
                if isinstance(cfg.get(key), bool) or not isinstance(cfg.get(key), (int, float)) or cfg[key] <= 0:
                    missing.append(key)
            if missing:
                raise PipelineError("Offene G0-Betreiberentscheidungen: " + ", ".join(missing) + f". Bearbeite {self.home / 'operator.yaml'}")
            binding = self.operating_binding()
            fingerprint = object_hash(binding)
            phrase = f"ICH BESTÄTIGE G0 {fingerprint[:12]}"
            if confirmation(f"{GATE_MEANING['G0']}\nKonfiguration: {self.home / 'operator.yaml'}\nSHA-256: {fingerprint}\nEingabe: {phrase}\n") != phrase:
                raise PipelineError("G0 wurde nicht bestätigt.")
            if not name.strip() or (not simulation and cfg["verantwortliche_person"] != name):
                raise PipelineError("Name muss der tatsächlich verantwortlichen Person in operator.yaml entsprechen.")
            record = {"gate": "G0", "name": name, "timestamp": now(), "binding": binding,
                      "kind": "DEMO_SIMULATION" if simulation else "HUMAN_OPERATOR", "meaning": GATE_MEANING["G0"]}
            archive = self.home / "approvals" / f"G0-{uuid4().hex}.json"
            write_json(archive, record, exclusive=True)
            write_json(self.home / ("G0.demo.json" if simulation else "G0.json"), record)
            return record

    def new(self, topic: str, *, demo: bool = False, audience: str | None = None, series: str = "Einzelepisode") -> str:
        if not topic.strip():
            raise PipelineError("Die Themenidee darf nicht leer sein.")
        self.setup()
        with self.lock():
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
            existing = {p.name for p in (self.home / "projects").glob(f"MA-{date}-*")}
            try:
                pid = next(f"MA-{date}-{i:03}" for i in range(1, 1000) if f"MA-{date}-{i:03}" not in existing)
            except StopIteration as exc:
                raise PipelineError("999 Projekte an einem Tag erreicht.") from exc
            root = self.project(pid)
            root.mkdir(parents=True, mode=0o700)
            for name in ["artifacts", "sources", "workers", "review", "freeze", "approvals", "attestations", "10_qa", "08_produktion/inbox"]:
                (root / name).mkdir(parents=True, exist_ok=True, mode=0o700)
            cfg = self.config()
            brief = {"projekt_id": pid, "themenidee": topic, "zielgruppe": audience or cfg.get("zielgruppe") or "STANDARDVORSCHLAG: Erwachsene",
                     "serienkontext": series, "budget_eur": cfg.get("budget_eur"), "zeitlimit_minuten": cfg.get("zeitlimit_minuten"), "beispiel": demo}
            write_json(root / "brief.json", brief, exclusive=True)
            write_json(root / "state.json", {"schema_version": 1, "projekt_id": pid, "demo": demo,
                       "current": {}, "approvals": {}, "reviews": {}, "attestations": {}, "reports": {},
                       "freeze": None, "invalidations": [], "created_at": now(), "worker_starts": 0}, exclusive=True)
            self.event(root, "PROJECT_CREATED", {"demo": demo})
            (root / "OPERATOR.md").write_text(f"{'DEMO — KEINE PRODUKTIVFREIGABE' if demo else 'PRODUKTION'}\n\nThema: {topic}\n\nNächster Befehl: ma run {pid}\nDaten liegen lokal. Keine Patienten- oder Zugangsdaten ablegen.\n", encoding="utf-8")
            return pid

    def state(self, pid: str) -> dict:
        return load_json(self.project(pid) / "state.json")

    def save(self, pid: str, state: dict):
        write_json(self.project(pid) / "state.json", state)

    def event(self, root: Path, kind: str, payload: dict):
        path = root / "events.jsonl"
        previous = None
        if path.is_file():
            lines = path.read_text(encoding="utf-8").splitlines()
            if lines:
                previous = json.loads(lines[-1])["sha256"]
        record = {"timestamp": now(), "event": kind, "payload": payload, "previous": previous}
        record["sha256"] = object_hash(record)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)

    def artifacts(self, pid: str, *, check_sources: bool = True) -> dict:
        root, state = self.project(pid), self.state(pid)
        result = {}
        for aid, reference in state["current"].items():
            path = contained(root, reference["path"])
            if digest(path) != reference["sha256"]:
                raise PipelineError(f"{aid}: Datei wurde außerhalb der Versionierung verändert. Rückweg: ma invalidate {pid} --change source --reason 'Datei verändert'")
            data = load_json(path)
            if data["artefakt_id"] != aid or data["version"] != reference["version"] or data["projekt_id"] != pid:
                raise PipelineError(f"{aid}: State-/Artefaktzuordnung inkonsistent.")
            result[aid] = data
        for aid, data in result.items():
            expected = set(DEPENDENCIES[aid])
            actual = {x["artefakt_id"] for x in data["eingaben"]}
            if actual != expected:
                raise PipelineError(f"{aid}: falscher Abhängigkeitsgraph.")
            for ref in data["eingaben"]:
                predecessor = state["current"].get(ref["artefakt_id"])
                if predecessor is None or ref["sha256"] != predecessor["sha256"] or ref["version"] != predecessor["version"]:
                    raise PipelineError(f"{aid}: veraltete Eingabe {ref['artefakt_id']}. Abhängige Artefakte erneut erstellen.")
        if check_sources and "A02" in result:
            self.verify_sources(root, result["A02"])
        return result

    def verify_sources(self, root: Path, artifact: dict):
        for source in artifact["inhalt"]["sources"]:
            if source["zugriff"] == "geprueft":
                if not source.get("original_geoeffnet") or not source.get("lokaler_pfad") or not source.get("sha256"):
                    raise PipelineError(f"{source['id']}: Originalquellenprüfung benötigt tatsächlichen Byte-Snapshot + SHA-256; ein Flag reicht nicht.")
                path = contained(root / "sources", source["lokaler_pfad"])
                if digest(path) != source["sha256"]:
                    raise PipelineError(f"{source['id']}: Originalquellen-Snapshot passt nicht zum Hash.")

    def envelope(self, pid: str, aid: str, content: dict, *, author: str = "ORCHESTRATOR") -> dict:
        state = self.state(pid)
        return {"artefakt_id": aid, "projekt_id": pid, "version": "0.1.0", "datum": now(), "autor": author,
                "status": "Entwurf", "eingaben": [], "quellen": [], "offene_punkte": [], "gesperrt": False,
                "sperrgrund": None, "beispiel": state["demo"], "inhalt": content}

    def latest_version(self, pid: str, aid: str) -> str | None:
        versions = [p.stem[1:] for p in (self.project(pid) / "artifacts" / aid).glob("v*.json")]
        return max(versions, key=lambda x: tuple(map(int, x.split(".")))) if versions else None

    def output_version(self, pid: str, aid: str, change: str = "minor") -> str:
        latest = self.latest_version(pid, aid)
        return next_version(latest, change) if latest else "0.1.0"

    def import_batch(self, pid: str, data: list[dict], *, internal: bool = False, change: str = "minor") -> list[str]:
        with self.lock(pid):
            return self._import(pid, data, internal=internal, change=change)

    def _import(self, pid: str, data: list[dict], *, internal: bool = False, change: str = "minor") -> list[str]:
        from .validation import validate_artifact
        if not isinstance(data, list) or not data:
            raise PipelineError("Übergabe benötigt eine nichtleere artifacts-Liste.")
        root, state = self.project(pid), self.state(pid)
        current = self.artifacts(pid)
        if len({a.get("artefakt_id") for a in data}) != len(data):
            raise PipelineError("Doppelte Artefakt-IDs in einer Übergabe.")
        candidate_state, candidate = copy.deepcopy(state), copy.deepcopy(current)
        pending = []
        for source in data:
            item = copy.deepcopy(source)
            aid = item.get("artefakt_id")
            if aid not in DEPENDENCIES:
                raise PipelineError("Unbekannte Artefakt-ID.")
            if not internal and aid not in [f"A{i:02}" for i in range(1, 8)]:
                raise PipelineError("A08–A12 werden ausschließlich vom Orchestrator aus echten Dateien/Operatornachweisen erstellt.")
            if item.get("projekt_id") != pid or item.get("beispiel") is not state["demo"]:
                raise PipelineError("Projekt-/DEMO-Zuordnung falsch. DEMO darf niemals Produktionsfreigaben erhalten.")
            if not internal and item.get("status") not in ("Entwurf", "geprüft"):
                raise PipelineError("Worker dürfen keine Freigabe, Produktion oder Veröffentlichung behaupten.")
            if not internal:
                self.import_prerequisites(pid, aid, state, current)
            previous = state["current"].get(aid)
            if previous:
                wanted = next_version(previous["version"], change)
                if item.get("version") != wanted:
                    raise PipelineError(f"{aid}: neue {change}-Version muss {wanted} sein. Vorherige Fassung bleibt unverändert.")
                self._invalidate_state(candidate_state, {aid}, f"Neue Version {wanted}", include_roots=False)
                for removed in set(candidate) - set(candidate_state["current"]):
                    candidate.pop(removed, None)
            elif item.get("version") != self.output_version(pid, aid, change):
                raise PipelineError(f"{aid}: nächste unveränderliche Fassung muss {self.output_version(pid, aid, change)} sein.")
            item["status"] = "Entwurf" if not internal else item["status"]
            item["eingaben"] = []
            for dep in DEPENDENCIES[aid]:
                if dep not in candidate_state["current"]:
                    raise PipelineError(f"{aid}: notwendige aktuelle Eingabe {dep} fehlt.")
                ref = candidate_state["current"][dep]
                item["eingaben"].append({"artefakt_id": dep, "version": ref["version"], "sha256": ref["sha256"]})
            candidate[aid] = item
            errors = validate_artifact(item, candidate, production=False)
            if errors:
                raise PipelineError(f"{aid} ungültig:\n" + "\n".join(errors))
            if aid == "A02":
                self.verify_sources(root, item)
            relative = f"artifacts/{aid}/v{item['version']}.json"
            if (root / relative).exists():
                raise PipelineError(f"Version existiert bereits: {relative}. Eine neue Version wählen.")
            reference = {"version": item["version"], "path": relative, "sha256": hashlib.sha256(canonical(item)).hexdigest()}
            candidate_state["current"][aid] = reference
            candidate[aid] = item
            pending.append((root / relative, item))
        for path, item in pending:
            write_json(path, item, exclusive=True)
        self.save(pid, candidate_state)
        self.event(root, "ARTIFACTS_IMPORTED", {"ids": [x["artefakt_id"] for x in data], "internal": internal})
        return [str(p) for p, _ in pending]

    def import_prerequisites(self, pid: str, aid: str, state: dict, artifacts: dict):
        if not self.g0_valid(state["demo"]):
            raise PipelineError("G0 fehlt oder ist veraltet. Keine Agentenarbeit vor Betriebsfreigabe.")
        for ids, gate in [(["A02", "A03"], "G1"), (["A04", "A05", "A06", "A07"], "G2")]:
            if aid in ids and not self.approval_valid(pid, gate):
                raise PipelineError(f"{aid} setzt die aktuelle menschliche Freigabe {gate} voraus.")

    def descendants(self, roots: set[str]) -> set[str]:
        found = set(roots)
        while True:
            next_set = found | {aid for aid, deps in DEPENDENCIES.items() if set(deps) & found}
            if next_set == found:
                return found
            found = next_set

    def _invalidate_state(self, state: dict, roots: set[str], reason: str, *, include_roots: bool = True):
        affected = self.descendants(roots)
        removed = affected if include_roots else affected - roots
        for aid in removed:
            state["current"].pop(aid, None)
        for gate, ids in GATE_ARTIFACTS.items():
            if set(ids) & affected:
                state["approvals"].pop(gate, None)
        state["freeze"] = None if affected & {f"A{i:02}" for i in range(1, 8)} else state["freeze"]
        if affected & {"A03", "A05", "A06"}:
            state["reviews"] = {}
        if affected & {"A08"}:
            state["attestations"] = {}
            state["reports"] = {}
        elif affected & {"A09"}:
            state["attestations"].pop("final", None)
            state["attestations"].pop("playback", None)
            state["reports"].pop("final", None)
        elif affected & {"A10", "A11"}:
            state["attestations"].pop("playback", None)
        state["invalidations"].append({"timestamp": now(), "roots": sorted(roots), "affected": sorted(affected), "reason": reason})

    def invalidate(self, pid: str, change: str, reason: str):
        mapping = {"source": {"A02"}, "meaning": {"A03"}, "wording": {"A04"},
                   "production": {"A06"}, "export": {"A09"}, "major": {"A01"}}
        if change not in mapping or not reason.strip():
            raise PipelineError("Gültiger Rückweg und ein konkreter Änderungsgrund sind erforderlich.")
        with self.lock(pid):
            state = self.state(pid)
            self._invalidate_state(state, mapping[change], reason)
            # Inbox-Dateien bleiben zur Nachvollziehbarkeit; werden erst durch neue gebundene Receipts nutzbar.
            self.save(pid, state)
            self.event(self.project(pid), "INVALIDATED", {"change": change, "reason": reason})
        return self.step(pid)

    def binding(self, pid: str, gate: str) -> dict:
        state, root = self.state(pid), self.project(pid)
        ids = GATE_ARTIFACTS[gate]
        bound = {aid: state["current"][aid] for aid in ids if aid in state["current"]}
        extras = {}
        if gate in ["G2", "G3", "G4", "G5a", "G5b"]:
            extras["reviews"] = state["reviews"]
        if gate in ["G3", "G4", "G5a", "G5b"]:
            revision = state["freeze"]
            extras["freeze"] = None if revision is None else {"revision": revision,
                "manifest_sha256": digest(root / "freeze" / revision / "manifest.json"),
                "sums_sha256": digest(root / "freeze" / revision / "SHA256SUMS")}
            handoff = root / "handoff/invideo"
            extras["invideo_handoff"] = {str(p.relative_to(handoff)): digest(p) for p in sorted(handoff.glob("*"))
                if p.is_file() and p.name in ["INVIDEO_PROMPT.txt", "SCENE_PLAN.md", "VOICEOVER.txt", "SUBTITLE_BASE.txt",
                    "ASSET_MANIFEST.yaml", "RIGHTS_CHECKLIST.md", "EXPECTED_OUTPUT.md", "OPERATOR_STEPS.md"]}
        if gate in ["G4", "G5a", "G5b"]:
            kinds = ["preview"] if gate == "G4" else (["final", "playback"] if gate == "G5b" else ["final"])
            extras["attestations"] = {k: state["attestations"].get(k) for k in kinds}
            extras["reports"] = {k: state["reports"].get(k) for k in kinds if k != "playback"}
            artifacts = self.artifacts(pid)
            pairs = [("A08", "preview")] if gate == "G4" else [("A09", "final"), ("A09", "srt")]
            for aid, key in pairs:
                if aid in artifacts:
                    ref = artifacts[aid]["inhalt"][key]
                    path = contained(root, ref["path"])
                    extras[key] = {"path": ref["path"], "sha256": digest(path)}
        if gate in ["G5a", "G5b"]:
            decisions = root / "handoff/youtube/YOUTUBE_DECISIONS.json"
            extras["youtube_decisions"] = digest(decisions) if decisions.is_file() else None
            handoff = root / "handoff/youtube"
            extras["youtube_handoff"] = {str(p.relative_to(handoff)): digest(p) for p in sorted(handoff.glob("*"))
                if p.is_file() and not p.name.endswith('.example.json') and p.name != 'YOUTUBE_DECISIONS.json'}
        if gate == "G5b":
            record = root / "youtube-private.json"
            extras["private_record"] = digest(record) if record.is_file() else None
        return {"artifacts": bound, "extras": extras, "operating": self.operating_binding(), "demo": state["demo"]}

    def approval_valid(self, pid: str, gate: str) -> bool:
        state, root = self.state(pid), self.project(pid)
        if not self.g0_valid(state["demo"]):
            return False
        ref = state["approvals"].get(gate)
        if ref is None:
            return False
        try:
            path = contained(root, ref["path"])
            record = load_json(path)
            if digest(path) != ref["sha256"] or record["binding"] != self.binding(pid, gate):
                return False
            if record["kind"] != ("DEMO_SIMULATION" if state["demo"] else "HUMAN_OPERATOR"):
                return False
            return bool(record["name"])
        except (PipelineError, KeyError):
            return False

    def promotion_plan(self, pid: str, ids: list[str]) -> tuple[dict, dict]:
        state = copy.deepcopy(self.state(pid))
        artifacts = self.artifacts(pid)
        planned = {}
        for aid in ids:
            item = copy.deepcopy(artifacts[aid])
            if item["status"] == "freigegeben" and int(item["version"].split(".")[0]) >= 1:
                continue
            item["status"] = "freigegeben"
            item["version"] = "1.0.0" if int(item["version"].split(".")[0]) == 0 else next_version(item["version"], "patch")
            item["datum"] = now()
            item["eingaben"] = [{"artefakt_id": dep, "version": state["current"][dep]["version"], "sha256": state["current"][dep]["sha256"]}
                               for dep in DEPENDENCIES[aid]]
            planned[aid] = item
            state["current"][aid] = {"version": item["version"], "path": f"artifacts/{aid}/v{item['version']}.json",
                                    "sha256": hashlib.sha256(canonical(item)).hexdigest()}
        return planned, {aid: state["current"][aid] for aid in ids}

    def _promote(self, pid: str, ids: list[str], prepared: dict | None = None):
        """Erste Freigabe 1.0.0; alle abhängigen Hashbezüge werden in neuen Versionen gebunden."""
        root, state = self.project(pid), self.state(pid)
        artifacts = self.artifacts(pid)
        if prepared is None:
            prepared, _ = self.promotion_plan(pid, ids)
        for aid in ids:
            if aid not in prepared:
                continue
            item = copy.deepcopy(artifacts[aid])
            if item["status"] == "freigegeben" and int(item["version"].split(".")[0]) >= 1:
                continue
            item = copy.deepcopy(prepared[aid])
            relative = f"artifacts/{aid}/v{item['version']}.json"
            write_json(root / relative, item, exclusive=True)
            state["current"][aid] = {"version": item["version"], "path": relative, "sha256": digest(root / relative)}
            artifacts[aid] = item
        self.save(pid, state)

    def review_packets(self, pid: str) -> dict:
        from .handoffs import build_review_packets
        return build_review_packets(self.project(pid), self.artifacts(pid))

    def reviews_valid(self, pid: str) -> list[str]:
        packets = self.review_packets(pid)
        state, root = self.state(pid), self.project(pid)
        problems = []
        for kind in ["medical", "legal"]:
            if not packets[f"{kind}_required"]:
                continue
            ref = state["reviews"].get(kind)
            if ref is None:
                problems.append(f"Pflicht-{kind}-Fachprüfung fehlt. Öffne {packets[kind + '_packet']}")
                continue
            path = contained(root, ref["path"])
            record = load_json(path)
            if (digest(path) != ref["sha256"] or record["decision"] != "approved"
                    or record["packet_sha256"] != packets[f"{kind}_packet_sha256"]):
                problems.append(f"{kind}-Review ist abgelehnt oder bezieht sich auf andere Claims/Formulierungen.")
        return problems

    def record_review(self, pid: str, kind: str, file: Path, confirmation: Callable[[str], str]) -> dict:
        if kind not in ("medical", "legal"):
            raise PipelineError("Review muss medical oder legal sein.")
        with self.lock(pid):
            state = self.state(pid)
            if state["demo"]:
                raise PipelineError("DEMO darf keine reale medizinische oder juristische Fachprüfung erhalten.")
            packets = self.review_packets(pid)
            decision = load_json(file)
            required = ["reviewer", "qualification", "notes", "reviewed_packet_sha256"]
            if any(not isinstance(decision.get(k), str) or not decision[k].strip() for k in required):
                raise PipelineError("Review benötigt echten Reviewer, Qualifikation, Begründung und Paket-Hash.")
            if decision.get("decision") not in ("approved", "rejected", "changes_required"):
                raise PipelineError("Ungültige Fachentscheidung.")
            if decision["reviewed_packet_sha256"] != packets[kind + "_packet_sha256"]:
                raise PipelineError("Fachentscheidung gilt nicht für das aktuelle Review-Paket.")
            artifacts = self.artifacts(pid)
            needed = {c["id"] for c in artifacts["A03"]["inhalt"]["claims"] if c["einsatz"] != "nein"}
            if not needed.issubset(set(decision.get("claim_ids", []))):
                raise PipelineError("Die Fachentscheidung muss sämtliche verwendbaren Claim-IDs abdecken.")
            phrase = f"ECHTE FACHPERSON {kind} {packets[kind + '_packet_sha256'][:12]}"
            if confirmation(f"Nur eine tatsächlich erfolgte Prüfung durch eine Fachperson dokumentieren.\nReviewer: {decision['reviewer']}\nEntscheidung: {decision['decision']}\nEingabe: {phrase}\n") != phrase:
                raise PipelineError("Fachprüfung nicht dokumentiert.")
            record = {**decision, "timestamp": now(), "packet_sha256": decision["reviewed_packet_sha256"], "kind": "HUMAN_EXPERT"}
            relative = f"review-records/{kind}-{uuid4().hex}.json"
            write_json(self.project(pid) / relative, record, exclusive=True)
            state["reviews"][kind] = {"path": relative, "sha256": digest(self.project(pid) / relative)}
            for gate in ["G2", "G3", "G4", "G5a", "G5b"]:
                state["approvals"].pop(gate, None)
            self.save(pid, state)
            self.event(self.project(pid), "EXPERT_REVIEW_RECORDED", {"kind": kind, "decision": decision["decision"]})
            return record

    def preflight(self, pid: str) -> str:
        from .handoffs import build_invideo
        from .validation import validate_bundle
        with self.lock(pid):
            state, root, artifacts = self.state(pid), self.project(pid), self.artifacts(pid)
            errors = validate_bundle({k: v for k, v in artifacts.items() if k <= "A07"}, production=not state["demo"])
            if not self.approval_valid(pid, "G2"):
                errors.append("Aktuelles G2 fehlt.")
            if "A07" not in artifacts or artifacts["A07"]["inhalt"]["ergebnis"] != "freigabefaehig":
                errors.append("Unabhängiger QA-Preflight ist nicht freigabefähig.")
            errors += self.reviews_valid(pid)
            if errors:
                raise PipelineError("Preflight blockiert:\n" + "\n".join(errors))
            if state["freeze"]:
                self.verify_freeze(pid)
                build_invideo(root, artifacts, state["freeze"])
                return state["freeze"]
            revision = next(f"r{i:03}" for i in range(1, 10000) if not (root / "freeze" / f"r{i:03}").exists())
            # BETA wurde noch nicht menschlich freigegeben. Die Kandidatenfassungen 1.0.0
            # werden vor dem Freeze vorbereitet; status bleibt Entwurf bis G3-Record gilt.
            for aid in ["A04", "A05", "A06", "A07"]:
                if artifacts[aid]["version"].startswith("0.") or (aid == "A07" and artifacts[aid]["inhalt"]["freeze"] != revision):
                    item = copy.deepcopy(artifacts[aid])
                    item["version"] = "1.0.0" if item["version"].startswith("0.") else self.output_version(pid, aid, "patch")
                    item["status"] = "geprüft"
                    if aid == "A07":
                        item["inhalt"]["freeze"] = revision
                    item["eingaben"] = [{"artefakt_id": dep, "version": state["current"][dep]["version"], "sha256": state["current"][dep]["sha256"]}
                                          for dep in DEPENDENCIES[aid]]
                    relative = f"artifacts/{aid}/v{item['version']}.json"
                    write_json(root / relative, item, exclusive=True)
                    state["current"][aid] = {"version": item["version"], "path": relative, "sha256": digest(root / relative)}
                    artifacts[aid] = item
            self.save(pid, state)
            freeze_binding = {aid: state["current"][aid] for aid in [f"A{i:02}" for i in range(1, 8)]}
            if state["freeze"]:
                meta = load_json(root / "freeze" / state["freeze"] / "manifest.json")
                if meta["artifact_binding"] == freeze_binding:
                    self.verify_freeze(pid)
                    build_invideo(root, artifacts, state["freeze"])
                    return state["freeze"]
            freeze = root / "freeze" / revision
            freeze.mkdir(mode=0o700)
            filelist = {}
            for aid in [f"A{i:02}" for i in range(1, 8)]:
                ref = state["current"][aid]
                filename = f"{aid}-v{ref['version']}.json"
                shutil.copyfile(root / ref["path"], freeze / filename)
                filelist[filename] = digest(freeze / filename)
            assets = artifacts["A06"]["inhalt"]["assets"]
            write_json(freeze / "assets-rights.json", assets, exclusive=True)
            filelist["assets-rights.json"] = digest(freeze / "assets-rights.json")
            write_json(freeze / "manifest.json", {"revision": revision, "projekt_id": pid, "demo": state["demo"],
                        "created_at": now(), "artifact_binding": freeze_binding, "files": filelist, "rules_sha256": self.rules_hash()}, exclusive=True)
            filelist["manifest.json"] = digest(freeze / "manifest.json")
            (freeze / "SHA256SUMS").write_text("".join(f"{value}  {key}\n" for key, value in sorted(filelist.items())), encoding="utf-8")
            state["freeze"] = revision
            self.save(pid, state)
            build_invideo(root, artifacts, revision)
            self.event(root, "FREEZE_CREATED", {"revision": revision, "hashes": filelist})
            return revision

    def verify_freeze(self, pid: str):
        state, root = self.state(pid), self.project(pid)
        if not state["freeze"]:
            raise PipelineError("Freeze fehlt.")
        freeze = root / "freeze" / state["freeze"]
        manifest = load_json(freeze / "manifest.json")
        expected_ids = {f"A{i:02}" for i in range(1, 8)}
        if (set(manifest.get("artifact_binding", {})) != expected_ids or manifest.get("revision") != state["freeze"]
                or manifest.get("projekt_id") != pid or manifest.get("demo") is not state["demo"]):
            raise PipelineError("Freeze-Pflichtbindungen, Projekt, Revision oder DEMO-Zuordnung sind inkonsistent.")
        expected_files = {f"{aid}-v{ref['version']}.json" for aid, ref in manifest["artifact_binding"].items()} | {"assets-rights.json"}
        if set(manifest.get("files", {})) != expected_files:
            raise PipelineError("Freeze-Manifest muss genau die Pflichtartefakte und Rechteverweise enthalten.")
        sums = (freeze / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        listed = {}
        for line in sums:
            value, filename = line.split("  ", 1)
            if filename in listed or digest(contained(freeze, filename)) != value:
                raise PipelineError(f"Freeze-Hash ungültig: {filename}")
            listed[filename] = value
        actual = {str(p.relative_to(freeze)) for p in freeze.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
        if set(listed) != actual or set(listed) != set(manifest["files"]) | {"manifest.json"}:
            raise PipelineError("Freeze-Dateiliste inkonsistent.")
        if any(listed.get(filename) != value for filename, value in manifest["files"].items()):
            raise PipelineError("Freeze-Manifest und SHA256SUMS widersprechen einander.")
        for aid, ref in manifest["artifact_binding"].items():
            if state["current"].get(aid) != ref:
                raise PipelineError(f"Freeze enthält veraltetes {aid}.")
            path = freeze / f"{aid}-v{ref['version']}.json"
            if digest(path) != ref["sha256"]:
                raise PipelineError(f"Freeze-Kopie stimmt nicht mit dem gebundenen Original {aid} überein.")
        if load_json(freeze / "assets-rights.json") != self.artifacts(pid)["A06"]["inhalt"]["assets"]:
            raise PipelineError("Freeze-Rechteverweise wurden gegenüber A06 verändert.")
        if manifest["rules_sha256"] != self.rules_hash():
            raise PipelineError("Regeln wurden nach Freeze geändert.")

    def gate_problems(self, pid: str, gate: str) -> list[str]:
        from .handoffs import build_invideo, build_youtube
        from .validation import validate_bundle
        state, root, artifacts = self.state(pid), self.project(pid), self.artifacts(pid)
        errors = []
        if gate not in GATES:
            return ["Unbekanntes Human Gate."]
        if not self.g0_valid(state["demo"]):
            errors.append("G0 fehlt oder ist nach Regel-/Konfigurationsänderung veraltet.")
        index = GATES.index(gate)
        if index and not self.approval_valid(pid, GATES[index - 1]):
            errors.append(f"Vorausgehendes Gate {GATES[index - 1]} fehlt oder ist veraltet.")
        for aid in GATE_ARTIFACTS[gate]:
            if aid not in artifacts:
                errors.append(f"{aid} fehlt.")
        errors += validate_bundle({k: v for k, v in artifacts.items() if k in GATE_ARTIFACTS[gate]}, production=not state["demo"])
        if gate in ["G2", "G3", "G4", "G5a", "G5b"] and "A03" in artifacts:
            errors += self.reviews_valid(pid)
        if gate in ["G3", "G4", "G5a", "G5b"]:
            try:
                self.verify_freeze(pid)
            except (PipelineError, OSError, ValueError) as exc:
                errors.append(str(exc))
            if "A07" in artifacts and artifacts["A07"]["inhalt"]["ergebnis"] != "freigabefaehig":
                errors.append("A07 ist nicht freigabefähig.")
            for filename in INVIDEO_FILES:
                path = root / "handoff/invideo" / filename
                if not path.is_file() or not path.read_bytes().strip():
                    errors.append(f"Pflicht-InVideo-Handoff fehlt/leer: {filename}. Wiederherstellen: ma repair-handoff {pid}")
            if all(aid in artifacts for aid in ["A04", "A05", "A06"]) and state["freeze"]:
                with tempfile.TemporaryDirectory(prefix="ma-invideo-expected-") as folder:
                    expected_dir = Path(folder)
                    build_invideo(root, artifacts, state["freeze"], output_path=expected_dir)
                    for filename in INVIDEO_FILES:
                        path = root / "handoff/invideo" / filename
                        if path.is_file() and digest(path) != digest(expected_dir / filename):
                            errors.append(f"InVideo-Handoff {filename} weicht von A04–A06 ab. Keine Freigabe für neue Texte ohne BETA/QA; ma repair-handoff {pid} stellt den geprüften Stand wieder her.")
        if gate in ["G4", "G5a", "G5b"]:
            kind = "preview" if gate == "G4" else "final"
            errors += self.media_problems(pid, kind)
        if gate in ["G5a", "G5b"]:
            for filename in YOUTUBE_FILES:
                path = root / "handoff/youtube" / filename
                if not path.is_file() or not path.read_bytes().strip():
                    errors.append(f"Pflicht-YouTube-Handoff fehlt/leer: {filename}. Wiederherstellen: ma repair-handoff {pid}")
            if "A09" in artifacts:
                media = artifacts["A09"]["inhalt"]
                with tempfile.TemporaryDirectory(prefix="ma-youtube-expected-") as folder:
                    expected_dir = Path(folder)
                    build_youtube(root, artifacts, contained(root, media["final"]["path"]), media["final"]["sha256"],
                                  contained(root, media["srt"]["path"]), output_path=expected_dir)
                    for filename in YOUTUBE_FILES:
                        path = root / "handoff/youtube" / filename
                        if path.is_file() and digest(path) != digest(expected_dir / filename):
                            errors.append(f"YouTube-Handoff {filename} weicht von A05/Final/SRT ab. Metadatenänderungen müssen über BETA/QA gehen; ma repair-handoff {pid} stellt Originale wieder her.")
            path = root / "handoff/youtube/YOUTUBE_DECISIONS.json"
            if not path.is_file():
                errors.append(f"YouTube-Entscheidungen offen. Kopiere/bearbeite {path.with_name('YOUTUBE_DECISIONS.example.json')}")
            else:
                decision = load_json(path)
                final = artifacts.get("A09", {}).get("inhalt", {}).get("final")
                srt = artifacts.get("A09", {}).get("inhalt", {}).get("srt")
                if decision.get("example") is not False or not final or not srt or decision.get("final_sha256") != final["sha256"] or decision.get("srt_sha256") != srt["sha256"]:
                    errors.append("YouTube-Entscheidungen müssen example=false und genau den aktuellen Final-/SRT-Hash tragen.")
                if not isinstance(decision.get("ki_kennzeichnung"), bool) or not isinstance(decision.get("werbung"), bool) or not str(decision.get("zielgruppe") or "").strip():
                    errors.append("KI-Kennzeichnung, Zielgruppe und Werbung müssen ausdrücklich entschieden werden.")
                if any(a.get("ki_illustration") for a in artifacts.get("A06", {}).get("inhalt", {}).get("assets", [])) and decision.get("ki_kennzeichnung") is not True:
                    errors.append("KI-Assets benötigen eine bestätigte Kennzeichnungsentscheidung.")
        if gate == "G5b":
            path = root / "youtube-private.json"
            if not path.is_file():
                errors.append("Tatsächlich privat hochgeladenes YouTube-Video wurde nicht zurückgemeldet.")
            else:
                private = load_json(path)
                final = artifacts.get("A09", {}).get("inhalt", {}).get("final")
                if not final or private["final_sha256"] != final["sha256"]:
                    errors.append(f"Privater Upload gehört zu anderem Export. Aktuelle Datei neu privat hochladen und ma youtube private {pid} zurückmelden.")
                if not self.attestation_valid(pid, "playback"):
                    errors.append("Echte Prüfung der verarbeiteten privaten Plattformfassung fehlt.")
        return errors

    def approve(self, gate: str, pid: str, name: str, confirmation_callback: Callable[[str], str], simulation: bool = False) -> dict:
        with self.lock(pid):
            state = self.state(pid)
            if state["demo"] != simulation:
                raise PipelineError("DEMO-Simulation und produktive menschliche Freigaben sind strikt getrennt.")
            if not name.strip():
                raise PipelineError("Der Name des tatsächlich bestätigenden Menschen ist erforderlich.")
            if gate in ["G5a", "G5b"]:
                self.sync_youtube_decisions(pid)
            errors = self.gate_problems(pid, gate)
            if errors:
                raise PipelineError(f"{gate} blockiert:\n" + "\n".join(errors))
            binding = self.binding(pid, gate)
            prepared = {}
            promote_ids = ["A01"] if gate == "G1" else (["A02", "A03"] if gate == "G2" else [])
            if promote_ids:
                prepared, planned_refs = self.promotion_plan(pid, promote_ids)
                binding = copy.deepcopy(binding)
                binding["artifacts"].update(planned_refs)
            fingerprint = object_hash(binding)
            phrase = f"{'DEMO SIMULATION' if simulation else 'ICH BESTÄTIGE'} {gate} {fingerprint[:12]}"
            artifacts_lines = "\n".join(f"  {aid} v{ref['version']} SHA-256 {ref['sha256']}" for aid, ref in binding["artifacts"].items())
            if confirmation_callback(f"{GATE_MEANING[gate]}\n{artifacts_lines}\nBindung SHA-256: {fingerprint}\nEingabe: {phrase}\n") != phrase:
                raise PipelineError("Keine Freigabe erteilt.")
            # G1/G2 haben noch keine downstream-Fassung: Statuswechsel erzeugt eine
            # neue, gebundene Erstfreigabe, niemals Überschreiben der Entwürfe.
            if gate == "G1":
                self._promote(pid, ["A01"], prepared)
            elif gate == "G2":
                self._promote(pid, ["A02", "A03"], prepared)
            actual_binding = self.binding(pid, gate)
            if actual_binding != binding:
                raise PipelineError("Artefakte oder Regeln wurden während der Bestätigung verändert. Keine Freigabe gespeichert; konkret erneut prüfen.")
            record = {"gate": gate, "projekt_id": pid, "name": name, "timestamp": now(), "binding": binding,
                      "kind": "DEMO_SIMULATION" if simulation else "HUMAN_OPERATOR", "meaning": GATE_MEANING[gate]}
            relative = f"approvals/{gate}-{uuid4().hex}.json"
            write_json(self.project(pid) / relative, record, exclusive=True)
            state = self.state(pid)
            state["approvals"][gate] = {"path": relative, "sha256": digest(self.project(pid) / relative)}
            self.save(pid, state)
            self.event(self.project(pid), "DEMO_GATE_SIMULATED" if simulation else "HUMAN_GATE_CONFIRMED", {"gate": gate, "binding": object_hash(binding)})
            return record

    def sync_youtube_decisions(self, pid: str):
        path = self.project(pid) / "handoff/youtube/YOUTUBE_DECISIONS.json"
        artifacts = self.artifacts(pid)
        if not path.is_file() or "A11" not in artifacts or "A09" not in artifacts:
            return
        data = load_json(path)
        media = artifacts["A09"]["inhalt"]
        if (data.get("example") is not False or data.get("final_sha256") != media["final"]["sha256"]
                or data.get("srt_sha256") != media["srt"]["sha256"] or not isinstance(data.get("ki_kennzeichnung"), bool)
                or not isinstance(data.get("werbung"), bool) or not isinstance(data.get("zielgruppe"), str) or not data["zielgruppe"].strip()):
            return
        item = copy.deepcopy(artifacts["A11"])
        decisions = {key: data[key] for key in ["ki_kennzeichnung", "zielgruppe", "werbung"]}
        if all(item["inhalt"].get(key) == value for key, value in decisions.items()):
            return
        item["inhalt"].update(decisions)
        item["version"] = self.output_version(pid, "A11")
        self._import(pid, [item], internal=True)

    def repair_handoff(self, pid: str):
        from .handoffs import build_invideo, build_youtube
        with self.lock(pid):
            self.verify_freeze(pid)
            root, state, artifacts = self.project(pid), self.state(pid), self.artifacts(pid)
            build_invideo(root, {aid: artifacts[aid] for aid in [f"A{i:02}" for i in range(1, 8)]}, state["freeze"])
            if "A09" in artifacts:
                media = artifacts["A09"]["inhalt"]
                build_youtube(root, artifacts, contained(root, media["final"]["path"]), media["final"]["sha256"], contained(root, media["srt"]["path"]))
            self.event(root, "HANDOFF_REGENERATED", {"freeze": state["freeze"], "human_gate_granted": False})
        return self.step(pid)

    def step(self, pid: str) -> dict:
        """Deterministische State-Machine: ein nächster Schritt, niemals Human-Autofreigabe."""
        state, root = self.state(pid), self.project(pid)
        artifacts = self.artifacts(pid)
        published = root / "youtube-published.json"
        if published.is_file() and artifacts.get("A11", {}).get("inhalt", {}).get("visibility") == "oeffentlich":
            record = load_json(published)
            final = artifacts.get("A09", {}).get("inhalt", {}).get("final")
            if not final or record["final_sha256"] != final["sha256"] or digest(contained(root, final["path"])) != final["sha256"]:
                raise PipelineError("Veröffentlichungsnachweis und aktuelle Finaldatei passen nicht zusammen.")
            return {"status": "PUBLISHED_REPORTED_BY_HUMAN", "gate": None, "project": pid,
                    "why": "Veröffentlichung vom Operator dokumentiert, nicht durch eine API verifiziert.", "next": [f"ma analytics {pid} --file analytics.json"]}
        def waiting(gate, why, steps):
            return {"status": "WAITING_FOR_HUMAN", "gate": gate, "why": why, "next": steps, "project": pid, "demo": state["demo"]}
        if not self.g0_valid(state["demo"]):
            return waiting("G0", "Betriebsfreigabe fehlt oder Regeln/Konfiguration geändert.", [f"Bearbeite {self.home / 'operator.yaml'}", "ma doctor", "ma approve G0 --name 'DEIN NAME'"])
        if "A01" not in artifacts:
            return {"status": "READY_FOR_WORKER", "role": "GAMMA", "project": pid}
        if not self.approval_valid(pid, "G1"):
            return waiting("G1", "Auftragsfreigabe fehlt.", [f"Prüfe {root / state['current']['A01']['path']}", f"ma approve G1 --project {pid} --name 'DEIN NAME'"])
        if "A02" not in artifacts:
            return {"status": "READY_FOR_WORKER", "role": "RESEARCH", "project": pid}
        if "A03" not in artifacts:
            return {"status": "READY_FOR_WORKER", "role": "ALPHA", "project": pid}
        if not self.approval_valid(pid, "G2"):
            packets = self.review_packets(pid)
            problems = self.reviews_valid(pid)
            steps = [f"Prüfe {root / state['current']['A03']['path']}"]
            for kind in ["medical", "legal"]:
                if packets[kind + "_required"]:
                    steps += [f"Lass {packets[kind + '_packet']} von einer echten Fachperson prüfen.", f"ma review {kind} --project {pid} --file {root / 'review' / (kind + '.decision.json')}"]
            steps.append(f"ma approve G2 --project {pid} --name 'DEIN NAME'")
            return waiting("G2", "; ".join(problems) or "Claims, Gegenbelege, Einschränkungen und Risiken benötigen inhaltliche Freigabe.", steps)
        if any(aid not in artifacts for aid in ["A04", "A05", "A06"]):
            return {"status": "READY_FOR_WORKER", "role": "BETA", "project": pid}
        if "A07" not in artifacts:
            return {"status": "READY_FOR_WORKER", "role": "QA_RED_TEAM", "project": pid}
        if not state["freeze"]:
            try:
                self.preflight(pid)
            except PipelineError as exc:
                return {"status": "BLOCKED", "gate": "G3", "why": str(exc), "next": [f"ma invalidate {pid} --change wording --reason 'Findings beheben'"], "project": pid}
            state = self.state(pid)
        if not self.approval_valid(pid, "G3"):
            return waiting("G3", "Preflight und Freeze vorbereitet; InVideo erst nach menschlicher Produktionsfreigabe starten.",
                           [f"Prüfe {root / 'freeze' / state['freeze']}", f"Prüfe {root / 'handoff/invideo/INVIDEO_PROMPT.txt'}", f"ma approve G3 --project {pid} --name 'DEIN NAME'"])
        if "A08" not in artifacts:
            return waiting("G3_INVIDEO", "Alles vorbereitet. Eine echte manuelle InVideo-Produktion steht aus.",
                           [f"Öffne {root / 'handoff/invideo/INVIDEO_PROMPT.txt'}", "Prüfe Kosten und erzeuge genau einen Entwurf in InVideo.",
                            f"Exportiere nach {root / '08_produktion/inbox/preview.mp4'} und subtitles.srt sowie (nach Vorschau-Freigabe) final.mp4.", f"ma resume {pid}"])
        if not self.approval_valid(pid, "G4"):
            return waiting("G4", "Echte Vorschau: technische QA und echte Smartphone-/Hör-/Bildprüfung erforderlich.",
                           [f"Prüfe {root / '10_qa'}", f"Fülle {root / 'handoff/invideo/PREVIEW_CHECKLIST.example.json'} als PREVIEW_CHECKLIST.json aus.",
                            f"ma attest {pid} --stage preview --file {root / 'handoff/invideo/PREVIEW_CHECKLIST.json'}", f"ma approve G4 --project {pid} --name 'DEIN NAME'"])
        if "A09" not in artifacts:
            return waiting("FINAL_EXPORT", "Konkrete Finaldatei und überprüfte SRT bereitstellen.", [f"Lege final.mp4 und subtitles.srt nach {root / '08_produktion/inbox'}", f"ma resume {pid}"])
        if not self.approval_valid(pid, "G5a"):
            return waiting("G5a", "Finaldatei-Hash, finale QA und Uploadentscheidungen benötigen menschliche Freigabe.",
                           [f"Prüfe {root / 'handoff/youtube/YOUTUBE_HANDOFF.md'}", f"Fülle {root / 'handoff/invideo/FINAL_CHECKLIST.example.json'} und YouTube-Entscheidungen aus.",
                            f"ma attest {pid} --stage final --file {root / 'handoff/invideo/FINAL_CHECKLIST.json'}", f"ma approve G5a --project {pid} --name 'DEIN NAME'"])
        if not (root / "youtube-private.json").is_file():
            return waiting("YOUTUBE_PRIVATE_UPLOAD", "Ausschließlich privat manuell hochladen.", [f"Öffne {root / 'handoff/youtube/YOUTUBE_HANDOFF.md'}", "Lade genau die hashgebundene Finaldatei privat hoch.", f"ma youtube private {pid} --id VIDEO_ID --url https://www.youtube.com/watch?v=VIDEO_ID"])
        if not self.approval_valid(pid, "G5b"):
            return waiting("G5b", "Verarbeitete private YouTube-Fassung tatsächlich prüfen.", [f"Öffne {root / 'handoff/playback/PLAYBACK_STEPS.md'}", f"ma attest {pid} --stage playback --file {root / 'handoff/playback/PLAYBACK_CHECKLIST.json'}", f"ma approve G5b --project {pid} --name 'DEIN NAME'"])
        if not (root / "youtube-published.json").is_file():
            return waiting("YOUTUBE_PUBLICATION", "Mensch darf jetzt manuell veröffentlichen; noch keine Veröffentlichung bestätigt.", ["Stelle das geprüfte private Video manuell öffentlich.", f"ma youtube published {pid} --url VIDEO_URL"])
        return {"status": "PUBLISHED_REPORTED_BY_HUMAN", "gate": None, "project": pid,
                "why": "Veröffentlichung vom Operator dokumentiert, nicht durch eine API verifiziert.", "next": [f"ma analytics {pid} --file analytics.json"]}

    def report(self, pid: str, kind: str) -> dict | None:
        ref = self.state(pid)["reports"].get(kind)
        if not ref:
            return None
        root = self.project(pid)
        path = contained(root, ref["path"])
        if digest(path) != ref["sha256"]:
            raise PipelineError(f"QA-Report {kind} wurde verändert.")
        report = load_json(path)
        for raw in report.get("raw_reports", []):
            rawpath = Path(raw["path"])
            if not rawpath.resolve().is_relative_to(root / "10_qa") or not rawpath.is_file() or digest(rawpath) != raw["sha256"]:
                raise PipelineError(f"Roher QA-Nachweis verändert: {rawpath}")
        return report

    def attestation_binding(self, pid: str, stage: str) -> dict:
        root, state = self.project(pid), self.state(pid)
        artifacts = self.artifacts(pid)
        if stage == "playback":
            private = load_json(root / "youtube-private.json")
            return {"private_sha256": digest(root / "youtube-private.json"), "final_sha256": private["final_sha256"],
                    "youtube_id": private["youtube_id"], "url": private["url"]}
        aid, key = ("A08", "preview") if stage == "preview" else ("A09", "final")
        if aid not in artifacts:
            raise PipelineError(f"{stage}: konkrete Mediendatei fehlt.")
        ref = artifacts[aid]["inhalt"][key]
        path = contained(root, ref["path"])
        report = self.report(pid, stage)
        if digest(path) != ref["sha256"] or not report or report["sha256"] != ref["sha256"]:
            raise PipelineError("Datei-/QA-Hash passen nicht. Technische QA erneut ausführen.")
        srt = root / "08_produktion/inbox/subtitles.srt"
        return {"stage": stage, "media_sha256": ref["sha256"], "report": state["reports"][stage],
                "srt_sha256": digest(srt) if srt.is_file() else None, "freeze": state["freeze"]}

    def attestation_valid(self, pid: str, stage: str) -> bool:
        state, root = self.state(pid), self.project(pid)
        ref = state["attestations"].get(stage)
        if not ref:
            return False
        try:
            path = contained(root, ref["path"])
            record = load_json(path)
            return (digest(path) == ref["sha256"] and record["binding"] == self.attestation_binding(pid, stage)
                    and record["kind"] == "HUMAN_OBSERVATION" and bool(record["operator"])
                    and all(record["checks"].get(k) is True for k in HUMAN_CHECKS + (PLAYBACK_CHECKS if stage == "playback" else [])))
        except (PipelineError, KeyError, OSError):
            return False

    def media_problems(self, pid: str, kind: str) -> list[str]:
        root, artifacts = self.project(pid), self.artifacts(pid)
        errors = []
        report = self.report(pid, kind)
        if not report:
            return [f"Tatsächliche {kind}-Videodatei wurde noch nicht technisch geprüft."]
        aid, field = ("A08", "preview") if kind == "preview" else ("A09", "final")
        if aid not in artifacts:
            return [f"{aid} fehlt."]
        ref = artifacts[aid]["inhalt"][field]
        if digest(contained(root, ref["path"])) != ref["sha256"] or report["sha256"] != ref["sha256"]:
            errors.append("Mediendatei wurde seit der QA verändert.")
        if not self.attestation_valid(pid, kind):
            errors.append(f"Echte vollständige {kind}-Bild-/Hör-/Smartphone-Prüfung fehlt oder ist veraltet.")
        ref_attest = self.state(pid)["attestations"].get(kind)
        attest = load_json(root / ref_attest["path"]) if ref_attest else {}
        allowed_manual = {"video_bitrate_target", "video_vbv_maxrate", "audio_bitrate",
                          "ending_visual_disclaimer", "audio_video_sync"}
        for check in report["checks"]:
            if check["status"] == "fehlgeschlagen":
                errors.append(f"K1 {check['id']}: {check.get('grund', '')} ({check.get('ist')} / Soll {check.get('soll')})")
            elif check["status"] == "nicht_geprueft":
                evidence = attest.get("technical_unknowns", {}).get(check["id"])
                if check["id"] not in allowed_manual or not isinstance(evidence, dict) or not evidence.get("nachweis") or not evidence.get("sha256"):
                    errors.append(f"Pflichtprüfung {check['id']} unvollständig: {check.get('grund', '')}")
                else:
                    try:
                        if digest(contained(root, evidence["nachweis"])) != evidence["sha256"]:
                            errors.append(f"Manueller technischer Nachweis {check['id']} passt nicht zum Hash.")
                    except PipelineError as exc:
                        errors.append(str(exc))
        if kind == "preview" and artifacts["A08"]["inhalt"]["render_real"] is not True:
            errors.append("Tatsächlicher InVideo-Render wurde vom Operator noch nicht bestätigt.")
        if kind == "final":
            srt_ref = artifacts["A09"]["inhalt"]["srt"]
            if digest(contained(root, srt_ref["path"])) != srt_ref["sha256"]:
                errors.append("SRT wurde nach QA verändert.")
            srt_report = report.get("subtitle_report")
            if not srt_report:
                errors.append("Formale SRT-Prüfung fehlt.")
            else:
                for check in srt_report["checks"]:
                    if check["status"] == "fehlgeschlagen":
                        errors.append(f"K1 Untertitel: {check['id']} {check.get('grund', '')}")
                    elif check["status"] == "nicht_geprueft":
                        mapping = {"srt_audio_sync": "subtitle_sync_100ms", "srt_burn_in": "burned_subtitles"}
                        if not attest.get("checks", {}).get(mapping.get(check["id"], "")):
                            errors.append(f"Untertitelpflicht {check['id']} nicht tatsächlich geprüft.")
            if not artifacts["A09"]["inhalt"]["musik_entfernt"]:
                audio = artifacts["A09"]["inhalt"]
                if not audio["getrennte_spuren"] or audio["ducking_db"] is None or not -21 <= audio["ducking_db"] <= -15:
                    errors.append("Musik ohne verlässliche getrennte Pegelmessung: Pflicht-Fallback Musik entfernen.")
        return errors

    def attest(self, pid: str, stage: str, file: Path, name: str, confirmation: Callable[[str], str]) -> dict:
        if stage not in ["preview", "final", "playback"]:
            raise PipelineError("Prüfstufe muss preview, final oder playback sein.")
        with self.lock(pid):
            state, root = self.state(pid), self.project(pid)
            if state["demo"]:
                raise PipelineError("Keine echte Hör-/Bild-/Smartphoneprüfung an DEMO vortäuschen.")
            if not name.strip():
                raise PipelineError("Name des tatsächlichen Prüfers erforderlich.")
            data = load_json(file)
            required_checks = HUMAN_CHECKS + (PLAYBACK_CHECKS if stage == "playback" else [])
            if any(data.get("checks", {}).get(key) is not True for key in required_checks):
                raise PipelineError("Alle anwendbaren manuellen Pflichtprüfungen müssen tatsächlich erledigt sein: " + ", ".join(required_checks))
            if data.get("example") is not False or data.get("checklist") != stage:
                raise PipelineError("Unausgefüllte Vorlage oder falsche Prüfstufe: example muss false und checklist muss der Stufe entsprechen.")
            if not isinstance(data.get("notes"), str) or not data["notes"].strip():
                raise PipelineError("Konkrete Beobachtungen zur Prüfung sind erforderlich.")
            required_gate = {"preview": "G3", "final": "G4", "playback": "G5a"}[stage]
            if not self.approval_valid(pid, required_gate):
                raise PipelineError(f"{required_gate} fehlt vor dieser Prüfung.")
            binding = self.attestation_binding(pid, stage)
            if stage == "playback":
                if any(data.get(key) != binding[key] for key in ["youtube_id", "url", "final_sha256"]):
                    raise PipelineError("Playback-Checkliste gehört zu einem anderen Video/Finalexport.")
            else:
                hash_key = "preview_sha256" if stage == "preview" else "final_sha256"
                if data.get(hash_key) != binding["media_sha256"] or data.get("freeze_id") != binding["freeze"]:
                    raise PipelineError("Checkliste gehört zu anderer Mediendatei oder Freeze-Revision.")
                if stage == "final" and data.get("srt_sha256") != binding["srt_sha256"]:
                    raise PipelineError("Finalcheckliste gehört zu einer anderen SRT-Version.")
            phrase = f"TATSÄCHLICH GEPRÜFT {stage} {object_hash(binding)[:12]}"
            if confirmation(f"Nur tatsächlich erfolgte Smartphone-, Hör-, Bild- und Syncprüfung bestätigen.\nSHA-256-Bindung: {object_hash(binding)}\nEingabe: {phrase}\n") != phrase:
                raise PipelineError("Manuelle Prüfung nicht bestätigt.")
            if stage == "preview":
                if data.get("render_invideo") is not True:
                    raise PipelineError("preview-Checkliste benötigt render_invideo=true ausschließlich nach echtem InVideo-Render.")
                item = copy.deepcopy(self.artifacts(pid)["A08"])
                item["inhalt"]["render_real"] = True
                item["inhalt"]["operator"] = name
                item["version"] = self.output_version(pid, "A08")
                # Neue Herkunftsdokumentation verwirft noch keine bestätigte G4-Fassung.
                reports = copy.deepcopy(state["reports"])
                self._import(pid, [item], internal=True)
                state = self.state(pid)
                state["reports"] = reports
                self.save(pid, state)
                binding = self.attestation_binding(pid, stage)
            if stage == "final":
                if not isinstance(data.get("musik_entfernt"), bool):
                    raise PipelineError("Final-Checkliste benötigt die tatsächlich geprüfte Musikentscheidung musik_entfernt=true/false.")
                if not data["musik_entfernt"]:
                    value = data.get("ducking_db")
                    if data.get("getrennte_spuren") is not True or isinstance(value, bool) or not isinstance(value, (int, float)) or not -21 <= value <= -15:
                        raise PipelineError("Keine zuverlässige getrennte Pegelmessung: Musik entfernen (Standard-Fallback).")
                    evidence = data.get("music_measurement")
                    if not isinstance(evidence, dict) or digest(contained(root, evidence.get("nachweis", ""))) != evidence.get("sha256"):
                        raise PipelineError("Realer Messnachweis für den Musik-/Stimmenabstand fehlt.")
                item = copy.deepcopy(self.artifacts(pid)["A09"])
                item["inhalt"].update({"musik_entfernt": data["musik_entfernt"], "getrennte_spuren": data.get("getrennte_spuren") is True,
                                      "ducking_db": data.get("ducking_db") if data.get("getrennte_spuren") is True else None})
                item["version"] = self.output_version(pid, "A09")
                reports = copy.deepcopy(state["reports"])
                attestations = copy.deepcopy(state["attestations"])
                self._import(pid, [item], internal=True)
                state = self.state(pid)
                state.update({"reports": reports, "attestations": attestations})
                self.save(pid, state)
                binding = self.attestation_binding(pid, stage)
            record = {**data, "stage": stage, "operator": name, "timestamp": now(), "binding": binding, "kind": "HUMAN_OBSERVATION"}
            relative = f"attestations/{stage}-{uuid4().hex}.json"
            write_json(root / relative, record, exclusive=True)
            state = self.state(pid)
            state["attestations"][stage] = {"path": relative, "sha256": digest(root / relative)}
            self.save(pid, state)
            if stage == "final":
                self._update_final_artifacts(pid)
            self.event(root, "HUMAN_OBSERVATION_RECORDED", {"stage": stage, "binding": object_hash(binding)})
            return record

    def qa(self, pid: str, path: Path, kind: str = "preview") -> dict:
        from .media import inspect_video
        from .subtitles import validate_srt
        from .handoffs import build_youtube
        if kind not in ["preview", "final"]:
            raise PipelineError("QA-Art muss preview oder final sein.")
        with self.lock(pid):
            root, state, artifacts = self.project(pid), self.state(pid), self.artifacts(pid)
            gate = "G3" if kind == "preview" else "G4"
            if not self.approval_valid(pid, gate):
                raise PipelineError(f"{gate} fehlt vor {kind}-Video-QA.")
            path = Path(path).resolve()
            if not path.is_file():
                raise PipelineError(f"Keine echte Datei vorhanden: {path}")
            destination = root / "08_produktion/inbox" / ("preview.mp4" if kind == "preview" else "final.mp4")
            if path != destination.resolve():
                if destination.is_file() and digest(destination) != digest(path):
                    raise PipelineError(f"Anderer Export existiert in {destination}. Verschiebe den bisherigen Export nachvollziehbar, bevor du einen neuen zurückgibst.")
                if not destination.exists():
                    shutil.copyfile(path, destination)
            file_hash = digest(destination)
            reportdir = root / "10_qa" / kind / uuid4().hex
            report = inspect_video(destination, reportdir)
            if kind == "final":
                srt = root / "08_produktion/inbox/subtitles.srt"
                if not srt.is_file():
                    raise PipelineError(f"Echte SRT-Datei fehlt: {srt}")
                report["subtitle_report"] = validate_srt(srt, self.config().get("font_path"))
            if report["sha256"] != file_hash or digest(destination) != file_hash:
                raise PipelineError("Video wurde während der Messung verändert; keine QA-Verwendbarkeit.")
            content = {"preview": {"path": str(destination.relative_to(root)), "sha256": file_hash},
                       "render_real": False, "operator": "Herkunft noch vom Menschen zu bestätigen", "render_zeitpunkt": now(), "freeze": state["freeze"]}
            if kind == "preview":
                item = self.envelope(pid, "A08", content)
                item["version"] = self.output_version(pid, "A08")
                self._import(pid, [item], internal=True)
            else:
                content = {"final": {"path": str(destination.relative_to(root)), "sha256": file_hash},
                           "srt": {"path": str(srt.relative_to(root)), "sha256": digest(srt)},
                           "aenderungen": ["Echte Finaldatei bereitgestellt; kein automatisches Neuencoding."],
                           "musik_entfernt": False, "getrennte_spuren": False, "ducking_db": None}
                item = self.envelope(pid, "A09", content)
                item["version"] = self.output_version(pid, "A09")
                self._import(pid, [item], internal=True)
            state = self.state(pid)
            reportpath = reportdir / "bound-report.json"
            write_json(reportpath, report, exclusive=True)
            state["reports"][kind] = {"path": str(reportpath.relative_to(root)), "sha256": digest(reportpath)}
            self.save(pid, state)
            checklist = root / "handoff/invideo" / f"{kind.upper()}_CHECKLIST.example.json"
            if checklist.is_file():
                example = load_json(checklist)
                example.update({"freeze_id": state["freeze"], "preview_sha256" if kind == "preview" else "final_sha256": file_hash})
                if kind == "final":
                    example["srt_sha256"] = digest(srt)
                write_json(checklist, example)
            if kind == "final":
                self._update_final_artifacts(pid)
                artifacts = self.artifacts(pid)
                build_youtube(root, artifacts, destination, file_hash, srt)
            self.event(root, "TECHNICAL_QA", {"kind": kind, "media_sha256": file_hash, "ergebnis": report["ergebnis"]})
            return report

    def _update_final_artifacts(self, pid: str):
        state, artifacts = self.state(pid), self.artifacts(pid)
        report = self.report(pid, "final")
        if not report or "A09" not in artifacts:
            return
        human_valid = self.attestation_valid(pid, "final")
        errors = self.media_problems(pid, "final")
        findings = [{"id": f"K1-{i:03}", "datei": "08_produktion/inbox/final.mp4", "problem": error,
                     "soll": "Pflichtprüfung bestanden und nachgewiesen", "ist": "offen", "schwere": "K1", "rueckweg": "Produktion/Postproduktion + QA erneut", "offen": True}
                    for i, error in enumerate(errors, 1)]
        checks = [{"id": key, "anwendbar": True, "erledigt": human_valid,
                   "nachweis": str(state["attestations"].get("final", {}).get("path", "Echte Prüfung fehlt"))} for key in HUMAN_CHECKS]
        combined_report = copy.deepcopy(report)
        combined_report["urspruenglicher_report"] = state["reports"]["final"]
        combined_report["human_resolutions"] = {}
        att_ref = state["attestations"].get("final")
        if human_valid and att_ref:
            att = load_json(self.project(pid) / att_ref["path"])
            combined_report["human_resolutions"] = {key: {**value, "attestation_sha256": att_ref["sha256"]}
                for key, value in att.get("technical_unknowns", {}).items()}
            if not errors:
                combined_report["ergebnis"] = "freigabefaehig"
        content = {"technische_reports": [combined_report], "findings": findings, "pflichtpruefungen": checks,
                   "ergebnis": "freigabefaehig" if not errors else ("nacharbeit_erforderlich" if any(c["status"] == "fehlgeschlagen" for c in report["checks"]) else "pruefung_unvollstaendig"),
                   "preview_sha256": artifacts["A08"]["inhalt"]["preview"]["sha256"], "final_sha256": artifacts["A09"]["inhalt"]["final"]["sha256"]}
        item = self.envelope(pid, "A10", content)
        item["version"] = self.output_version(pid, "A10")
        # A10 updates must not silently discard already-bound media measurements.
        preserved = {k: copy.deepcopy(state[k]) for k in ["reports", "attestations"]}
        self._import(pid, [item], internal=True)
        state = self.state(pid)
        state.update(preserved)
        self.save(pid, state)
        artifacts = self.artifacts(pid)
        content11 = {"final_sha256": content["final_sha256"], "youtube_id": None, "url": None, "visibility": "vorbereitet",
                     "ki_kennzeichnung": None, "zielgruppe": None, "werbung": None, "playback_pruefung": None, "veroeffentlicht_am": None}
        item11 = self.envelope(pid, "A11", content11)
        item11["version"] = self.output_version(pid, "A11")
        self._import(pid, [item11], internal=True)

    def resume_media(self, pid: str) -> None:
        root, state, artifacts = self.project(pid), self.state(pid), self.artifacts(pid)
        preview = root / "08_produktion/inbox/preview.mp4"
        final = root / "08_produktion/inbox/final.mp4"
        if self.approval_valid(pid, "G3") and preview.is_file():
            ref = artifacts.get("A08", {}).get("inhalt", {}).get("preview")
            if not ref or digest(preview) != ref["sha256"]:
                self.qa(pid, preview, "preview")
        if self.approval_valid(pid, "G4") and final.is_file():
            artifacts = self.artifacts(pid)
            ref = artifacts.get("A09", {}).get("inhalt", {}).get("final")
            srt = root / "08_produktion/inbox/subtitles.srt"
            srtref = artifacts.get("A09", {}).get("inhalt", {}).get("srt")
            if not ref or digest(final) != ref["sha256"] or (srt.is_file() and (not srtref or digest(srt) != srtref["sha256"])):
                self.qa(pid, final, "final")

    def youtube_private(self, pid: str, video_id: str, url: str, name: str, confirmation: Callable[[str], str]) -> dict:
        from .handoffs import build_playback
        with self.lock(pid):
            state, root = self.state(pid), self.project(pid)
            if state["demo"] or not self.approval_valid(pid, "G5a"):
                raise PipelineError("Aktuelle produktive G5a-Freigabe fehlt. Kein privater Upload wird behauptet.")
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) or url not in (f"https://www.youtube.com/watch?v={video_id}", f"https://youtu.be/{video_id}"):
                raise PipelineError("Gültige zusammenpassende YouTube-Video-ID und URL erforderlich.")
            phrase = f"PRIVAT HOCHGELADEN {video_id}"
            if not name.strip() or confirmation(f"Nur tatsächlich selbst privat hochgeladenes Video dokumentieren.\n{url}\nEingabe: {phrase}\n") != phrase:
                raise PipelineError("Privater Upload nicht dokumentiert.")
            final = self.artifacts(pid)["A09"]["inhalt"]["final"]
            record = {"youtube_id": video_id, "url": url, "visibility": "privat", "operator": name,
                      "timestamp": now(), "final_sha256": final["sha256"], "kind": "HUMAN_REPORTED_NOT_API_VERIFIED"}
            existing = root / "youtube-private.json"
            if existing.is_file():
                archive = root / "youtube-history" / f"private-{uuid4().hex}.json"
                archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(existing, archive)
            write_json(existing, record)
            state["attestations"].pop("playback", None)
            state["approvals"].pop("G5b", None)
            self.save(pid, state)
            build_playback(root, record, final["sha256"])
            self.event(root, "PRIVATE_UPLOAD_REPORTED", {"video_id": video_id})
            return record

    def youtube_published(self, pid: str, url: str, name: str, confirmation: Callable[[str], str]) -> dict:
        with self.lock(pid):
            state, root = self.state(pid), self.project(pid)
            if state["demo"] or not self.approval_valid(pid, "G5b"):
                raise PipelineError("Aktuelle produktive G5b-Freigabe fehlt.")
            private = load_json(root / "youtube-private.json")
            if url != private["url"]:
                raise PipelineError("Veröffentlichungs-URL muss dem geprüften privaten Video entsprechen.")
            phrase = f"ÖFFENTLICH VERÖFFENTLICHT {private['youtube_id']}"
            if not name.strip() or confirmation(f"Nur tatsächlich erfolgte manuelle Veröffentlichung dokumentieren.\nEingabe: {phrase}\n") != phrase:
                raise PipelineError("Veröffentlichung nicht dokumentiert.")
            record = {**private, "visibility": "oeffentlich", "published_at": now(), "operator": name}
            record["g5b_approval"] = copy.deepcopy(state["approvals"]["G5b"])
            item = copy.deepcopy(self.artifacts(pid)["A11"])
            decisions = load_json(root / "handoff/youtube/YOUTUBE_DECISIONS.json")
            item["inhalt"].update({"youtube_id": private["youtube_id"], "url": url, "visibility": "oeffentlich", "veroeffentlicht_am": record["published_at"],
                                  "ki_kennzeichnung": decisions["ki_kennzeichnung"], "zielgruppe": decisions["zielgruppe"], "werbung": decisions["werbung"],
                                  "playback_pruefung": state["attestations"]["playback"]})
            item["version"] = self.output_version(pid, "A11")
            item["status"] = "veröffentlicht"
            # Der Veröffentlichungsnachweis ergänzt A11. Historische G5-Bindungen bleiben
            # erhalten und werden für Analytics ausdrücklich über ihren damaligen Hash geprüft.
            approvals = copy.deepcopy(state["approvals"])
            self._import(pid, [item], internal=True)
            state = self.state(pid)
            state["approvals"] = approvals
            self.save(pid, state)
            existing = root / "youtube-published.json"
            if existing.is_file():
                archive = root / "youtube-history" / f"published-{uuid4().hex}.json"
                archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(existing, archive)
            write_json(existing, record)
            self.event(root, "PUBLICATION_REPORTED", {"video_id": private["youtube_id"]})
            return record

    def analytics(self, pid: str, file: Path):
        with self.lock(pid):
            root, state = self.project(pid), self.state(pid)
            if state["demo"] or not (root / "youtube-published.json").is_file():
                raise PipelineError("Reale Analytics erst nach vom Menschen dokumentierter Veröffentlichung.")
            artifacts = self.artifacts(pid)
            publication = artifacts.get("A11", {}).get("inhalt", {})
            published = load_json(root / "youtube-published.json")
            final = artifacts.get("A09", {}).get("inhalt", {}).get("final")
            if (publication.get("visibility") != "oeffentlich" or not final or published["final_sha256"] != final["sha256"]
                    or publication.get("final_sha256") != final["sha256"] or publication.get("youtube_id") != published["youtube_id"]
                    or publication.get("url") != published["url"] or digest(contained(root, final["path"])) != final["sha256"]):
                raise PipelineError("Analytics dürfen nur zur aktuell dokumentierten öffentlichen Version gehören; alter Veröffentlichungsmarker ist veraltet.")
            data = load_json(file)
            for key in ["datenquelle", "zeitraum", "metriken", "beobachtungen", "hypothesen", "naechster_test"]:
                if key not in data:
                    raise PipelineError(f"Analytics-Pflichtfeld fehlt: {key}")
            if not Path(file).is_file() or not data["datenquelle"]:
                raise PipelineError("Reale Datenquelle erforderlich.")
            for key in ["views", "average_percentage_viewed", "swipe_away_1s", "swipe_away_3s", "returning_viewers", "ctr"]:
                data["metriken"].setdefault(key, {"wert": None, "begruendung": "Im bereitgestellten Export nicht verfügbar."})
            data["regel_aenderung"] = False
            item = self.envelope(pid, "A12", data, author="ORCHESTRATOR aus realem Operator-Export")
            item["version"] = self.output_version(pid, "A12")
            self._import(pid, [item], internal=True)
            archive = root / "analytics-inputs" / f"{uuid4().hex}.json"
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, archive)
            self.event(root, "ANALYTICS_IMPORTED", {"source_sha256": digest(archive), "artifact": "A12"})
            return item
