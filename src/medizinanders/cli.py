from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import Pipeline
from .errors import PipelineError
from .util import load_json
from .workers import capabilities, execute_worker, import_worker_result


def repo_path() -> Path:
    configured = os.environ.get("MA_REPO")
    candidate = Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]
    if not (candidate / "config/channel.yaml").is_file():
        raise PipelineError("Pipeline-Dateien fehlen. Aus dem Git-Checkout installieren: python3 -m pip install -e .")
    return candidate


def operator_confirmation(prompt: str) -> str:
    """Keine --yes Option. Nur ein bedienender Mensch soll diesen Pfad aufrufen."""
    if not sys.stdin.isatty():
        raise PipelineError("Menschliche Bestätigung benötigt ein interaktives Terminal. Agenten dürfen approve/review/attest nicht ausführen.")
    print(prompt, end="", flush=True)
    return input("> ").strip()


def display(state: dict, *, as_json: bool = False):
    if as_json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    print(f"STATUS: {state.get('status', 'OK')}")
    if state.get("demo"):
        print("MODE: DEMO — KEINE PRODUKTIVFREIGABE")
    for key, label in [("project", "PROJECT"), ("gate", "GATE"), ("role", "WORKER"), ("why", "WHY")]:
        if state.get(key):
            print(f"{label}: {state[key]}")
    if state.get("next"):
        print("\nNext:")
        for index, item in enumerate(state["next"], 1):
            print(f"{index}. {item}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MedizinAnders — lokale Codex-Pipeline mit echten Human Gates")
    p.add_argument("--home", type=Path, default=Path(os.environ.get("MA_HOME", "~/.local/share/medizinanders")).expanduser(), help="Privater Datenspeicher außerhalb des Repositories")
    p.add_argument("--json", action="store_true", help="Maschinenlesbarer Status")
    subs = p.add_subparsers(dest="command", required=True)
    subs.add_parser("setup", help="Persönliche lokale G0-Konfiguration anlegen")
    subs.add_parser("doctor", help="Tatsächlich vorhandene Werkzeuge anzeigen, keine Login-Funktion vortäuschen")
    new = subs.add_parser("new", help="Neuen echten Videoauftrag anlegen")
    new.add_argument("--topic", help="Themenidee, alternativ interaktiv")
    new.add_argument("--audience")
    new.add_argument("--series", default="Einzelepisode")
    for name in ["run", "resume", "status"]:
        child = subs.add_parser(name)
        child.add_argument("project")
        if name != "status":
            child.add_argument("--prepare-only", action="store_true", help="Isolierten Kontext für native Subagents in einer bestehenden Codex-Sitzung vorbereiten")
    approve = subs.add_parser("approve", help="Nur Operator: konkrete hashgebundene Freigabe interaktiv bestätigen")
    approve.add_argument("gate", choices=["G0", "G1", "G2", "G3", "G4", "G5a", "G5b"])
    approve.add_argument("--project")
    approve.add_argument("--name", required=True)
    imp = subs.add_parser("import", help="Ergebnis eines vom Orchestrator erzeugten Worker-Kontexts importieren")
    imp.add_argument("project")
    imp.add_argument("--file", type=Path, required=True)
    inv = subs.add_parser("invalidate", help="Abhängige Artefakte/Freigaben nachvollziehbar invalidieren")
    inv.add_argument("project")
    inv.add_argument("--change", required=True, choices=["source", "meaning", "wording", "production", "export", "major"])
    inv.add_argument("--reason", required=True)
    review = subs.add_parser("review", help="Nur Operator: echte medizinische/juristische Fachentscheidung dokumentieren")
    review.add_argument("kind", choices=["medical", "legal"])
    review.add_argument("--project", required=True)
    review.add_argument("--file", type=Path, required=True)
    attest = subs.add_parser("attest", help="Nur Operator: tatsächlich erfolgte manuelle Medienprüfung dokumentieren")
    attest.add_argument("project")
    attest.add_argument("--stage", choices=["preview", "final", "playback"], required=True)
    attest.add_argument("--file", type=Path, required=True)
    attest.add_argument("--name", help="Tatsächlicher Prüfer; Default verantwortliche Person")
    qa = subs.add_parser("qa", help="Echte MP4 technisch prüfen; niemals automatisch neu encodieren")
    qa.add_argument("project")
    qa.add_argument("--file", type=Path, required=True)
    qa.add_argument("--kind", choices=["preview", "final"], default="preview")
    freeze = subs.add_parser("verify-freeze")
    freeze.add_argument("project")
    repair = subs.add_parser("repair-handoff", help="Abgeleitete Handoff-Dateien aus unveränderten Originalen wiederherstellen")
    repair.add_argument("project")
    youtube = subs.add_parser("youtube", help="Nur Operator: reale manuelle Plattformaktionen dokumentieren")
    yt = youtube.add_subparsers(dest="youtube_action", required=True)
    for action in ["private", "published"]:
        child = yt.add_parser(action)
        child.add_argument("project")
        child.add_argument("--url", required=True)
        child.add_argument("--name")
        if action == "private":
            child.add_argument("--id", required=True)
    analytics = subs.add_parser("analytics", help="Reale Analytics-Daten übernehmen; fehlende Werte bleiben null")
    analytics.add_argument("project")
    analytics.add_argument("--file", type=Path, required=True)
    demo = subs.add_parser("demo", help="Synthetischer isolierter Test ohne reale Freigaben/Uploads")
    demo.add_argument("--output", type=Path, default=None)
    demo.add_argument("--with-video", action="store_true", help="Tatsächliche falsche DEMO-Videofixture technisch prüfen")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        pipeline = Pipeline(args.home, repo_path())
        cmd = args.command
        if cmd == "setup":
            path = pipeline.setup()
            print(f"Lokale Konfiguration: {path}\nFülle die offenen Felder aus. Danach: ma doctor und ma approve G0 --name 'DEIN NAME'")
        elif cmd == "doctor":
            result = capabilities()
            if (pipeline.home / "operator.yaml").is_file():
                result["g0_valid"] = pipeline.g0_valid()
            result["storage"] = str(pipeline.home)
            result["human_gates"] = "Nur interaktive Operator-Befehle; keine Agentfreigabe"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("Codex-Binärdatei/Weboption vorhanden ≠ Anmeldung/Webzugriff funktioniert. Reale Worker testen den Zugriff und blockieren bei Fehlern.")
        elif cmd == "new":
            topic = args.topic
            if not topic:
                if not sys.stdin.isatty():
                    raise PipelineError("Themenidee fehlt. Verwende: ma new --topic 'DEIN THEMA'")
                topic = input("Themenidee für die neue Episode: ").strip()
            pid = pipeline.new(topic, audience=args.audience, series=args.series)
            print(f"PROJECT: {pid}\nSTORAGE: {pipeline.project(pid)}\nNext: ma run {pid}")
        elif cmd in ["run", "resume", "status"]:
            if cmd == "resume":
                pipeline.resume_media(args.project)
            state = pipeline.step(args.project)
            while cmd != "status" and state.get("status") == "READY_FOR_WORKER":
                print(f"Starte isolierten nativen Worker: {state['role']}", flush=True)
                workspace = execute_worker(pipeline, args.project, state["role"], prepare_only=args.prepare_only)
                if args.prepare_only:
                    state = {"status": "WAITING_FOR_CODEX_NATIVE_WORKER", "role": state["role"], "project": args.project,
                             "why": "Minimaler Kontext vorbereitet; Worker in verfügbarer nativer Codex-Sitzung starten.",
                             "next": [f"Öffne {workspace / 'START_HERE.md'}", f"ma import {args.project} --file {workspace / 'result.json'}", f"ma resume {args.project}"]}
                    break
                state = pipeline.step(args.project)
            display(state, as_json=args.json)
        elif cmd == "approve":
            if args.gate == "G0":
                pipeline.approve_g0(args.name, operator_confirmation)
                print("G0 menschlich dokumentiert. Next: ma new")
            else:
                if not args.project:
                    raise PipelineError("--project ist für diesen konkreten Gate erforderlich.")
                pipeline.approve(args.gate, args.project, args.name, operator_confirmation)
                display(pipeline.step(args.project), as_json=args.json)
        elif cmd == "import":
            import_worker_result(pipeline, args.project, args.file)
            display(pipeline.step(args.project), as_json=args.json)
        elif cmd == "invalidate":
            display(pipeline.invalidate(args.project, args.change, args.reason), as_json=args.json)
        elif cmd == "review":
            pipeline.record_review(args.project, args.kind, args.file, operator_confirmation)
            display(pipeline.step(args.project), as_json=args.json)
        elif cmd == "attest":
            name = args.name or pipeline.config().get("verantwortliche_person", "")
            pipeline.attest(args.project, args.stage, args.file, name, operator_confirmation)
            display(pipeline.step(args.project), as_json=args.json)
        elif cmd == "qa":
            report = pipeline.qa(args.project, args.file, args.kind)
            print(f"QA: {report['ergebnis']}\nSHA-256: {report['sha256']}\nReports: {pipeline.project(args.project) / '10_qa'}")
            display(pipeline.step(args.project), as_json=args.json)
        elif cmd == "verify-freeze":
            pipeline.verify_freeze(args.project)
            print("Freeze-Hashes und aktuelle Artefaktbindung gültig.")
        elif cmd == "repair-handoff":
            display(pipeline.repair_handoff(args.project), as_json=args.json)
        elif cmd == "youtube":
            name = args.name or pipeline.config().get("verantwortliche_person", "")
            if args.youtube_action == "private":
                pipeline.youtube_private(args.project, args.id, args.url, name, operator_confirmation)
            else:
                pipeline.youtube_published(args.project, args.url, name, operator_confirmation)
            display(pipeline.step(args.project), as_json=args.json)
        elif cmd == "analytics":
            pipeline.analytics(args.project, args.file)
            print("A12 aus bereitgestellten realen Daten gespeichert. Genau ein nächster Test; keine automatische Regeländerung.")
        elif cmd == "demo":
            from .demo import run_demo
            result = run_demo(args.output or pipeline.home, pipeline.repo, args.with_video)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            else:
                print(f"DEMO: bestanden; echte Freigaben/Uploads: 0\nPROJECT: {result['projekt_id']}\nREPORT: {result['report_path']}")
                display(result["next"])
        return 0
    except (PipelineError, OSError, ValueError, KeyError) as exc:
        print(f"STATUS: BLOCKED\nWHY: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
