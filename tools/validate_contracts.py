#!/usr/bin/env python3
"""Validate shared contracts (roadmap 1.14.10/11).

* every schema in packages/contracts/schemas is a valid draft 2020-12 schema;
* fixtures/valid/<name>.*.json validate, fixtures/invalid/<name>.*.json are rejected;
* real producers validate: capabilities.yml, the desktop release-manifest.json
  produced by tools/build_desktop_installer.py, and a Sync & Build record
  converted by aiwb.github.orchestrator.build_metadata().

Requires jsonschema and pyyaml.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
C = REPO / "packages/contracts"


def main() -> int:
    import jsonschema
    import yaml

    errors: list[str] = []
    schemas = {}
    for p in sorted((C / "schemas").glob("*.schema.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(s)
        schemas[p.name.removesuffix(".schema.json")] = jsonschema.Draft202012Validator(s)
    if not schemas:
        errors.append("no schemas found")

    def schema_for(path: Path) -> str | None:
        return next((n for n in schemas if path.name.startswith(n + ".")), None)

    count = 0
    for kind in ("valid", "invalid"):
        for p in sorted((C / "fixtures" / kind).glob("*.json")):
            name = schema_for(p)
            if name is None:
                errors.append(f"{p.name}: no matching schema")
                continue
            ok = not list(schemas[name].iter_errors(json.loads(p.read_text(encoding="utf-8"))))
            count += 1
            if ok != (kind == "valid"):
                errors.append(f"{kind}/{p.name}: expected {'valid' if kind == 'valid' else 'rejected'}")

    caps = yaml.safe_load((REPO / "capabilities.yml").read_text(encoding="utf-8"))
    errors += [f"capabilities.yml: {e.message}" for e in schemas["capabilities.v1"].iter_errors(caps)]
    ids = [c["id"] for c in caps.get("capabilities", []) if isinstance(c, dict) and "id" in c]
    if len(ids) != len(set(ids)):
        errors.append("capabilities.yml: duplicate ids")

    with tempfile.TemporaryDirectory() as t:
        r = subprocess.run([sys.executable, str(REPO / "tools/build_desktop_installer.py"), "--out", t], capture_output=True, text=True)
        if r.returncode != 0:
            errors.append("desktop builder failed: " + r.stderr[-300:])
        else:
            m = json.loads((Path(t) / "release-manifest.json").read_text(encoding="utf-8"))
            errors += [f"desktop release-manifest.json: {e.message}" for e in schemas["release-manifest.v1"].iter_errors(m)]

    sys.path.insert(0, str(REPO / "apps/desktop/src"))
    from aiwb.github import orchestrator as orc
    rec = {"git": {"operation_id": "sb-1", "repository": "o/r", "branch": "work", "commit_sha": "d" * 40, "pushed": True},
           "build": {"operation_id": "sb-1", "workflow_file": ".github/workflows/ci.yml", "run_id": 5, "outcome": "success",
                     "artifacts": [{"artifact_id": 1, "name": "a", "sha256": "e" * 64, "verification": "matched", "path": "x", "size": 1}]}}
    meta = orc.build_metadata(rec, repository_id=3)
    errors += [f"orchestrator build_metadata: {e.message}" for e in schemas["build-metadata.v1"].iter_errors(meta)]

    # V2 producers (roadmap 1.17–2.0): real store/snapshot/handoff output must satisfy the contracts.
    import tempfile as _tf
    from aiwb.v2 import V2Project, build_snapshot
    from aiwb.v2.handoff import find_manifest
    with _tf.TemporaryDirectory() as t:
        p = V2Project(Path(t), "contract-check")
        p.open()
        task = p.tasks.transition(p.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer"})["task_id"], "ready")
        h = p.handoffs.prepare(task["task_id"], "agent-implementer")
        ev = p.evidence.record(type="model_report", subject_type="task", subject_id=task["task_id"], source_kind="model", result="claimed")
        st = p.store.load()
        errors += [f"v2 agents/tasks: {e.message}" for e in schemas["agent-task.v1"].iter_errors(
            {"agents": list(st["agents"].values()), "tasks": list(st["tasks"].values())})]
        errors += [f"v2 snapshot: {e.message}" for e in schemas["project-state.v1"].iter_errors(build_snapshot(st))]
        ev_schema = jsonschema.Draft202012Validator({"$defs": schemas["project-state.v1"].schema["$defs"], "$ref": "#/$defs/evidence"})
        errors += [f"v2 evidence: {e.message}" for e in ev_schema.iter_errors(ev)]
        example = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"], "task_revision": 1,
                   "attempt_id": h["attempt_id"], "outcome": "complete", "summary": "s"}
        errors += [f"v2 handoff manifest: {e.message}" for e in schemas["handoff.v1"].iter_errors(
            find_manifest("<<<AIWB_HANDOFF>>>\n" + json.dumps(example) + "\n<<<AIWB_END_HANDOFF>>>"))]
        led = schemas["event-ledger.v1"]
        for rec in p.store.ledger.all():
            errors += [f"v2 event ledger {rec.get('event_id')}: {e.message}" for e in led.iter_errors(rec)]
    # Project Charter (3.4.0): schema and code validator agree on every fixture.
    from aiwb.v2.charter import validate_charter
    for kind in ("valid", "invalid"):
        for fx in sorted((C / "fixtures" / kind).glob("project-charter.v1.*.json")):
            code_ok = not validate_charter(json.loads(fx.read_text(encoding="utf-8")))["errors"]
            if code_ok != (kind == "valid"):
                errors.append(f"aiwb.v2.charter disagrees with fixture {kind}/{fx.name}")
    r = subprocess.run([sys.executable, str(REPO / "tools/gen_v2_contracts.py"), "--check"], capture_output=True, text=True)
    if r.returncode != 0:
        errors.append(r.stdout.strip())

    for e in errors:
        print("FAIL:", e)
    print(f"{'FAIL' if errors else 'PASS'}: {len(schemas)} schemas, {count} fixtures, capabilities ({len(ids)}), desktop manifest, build metadata, V2 producers, charter")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
