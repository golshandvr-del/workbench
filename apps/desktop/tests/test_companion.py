"""Companion (Integration Spec §11.2, P3.1–P3.3): envelope, pairing with desktop approval, permissions,
revocation, replay/expiry, central-service routing and the real LAN HTTP endpoint."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.companion import crypto  # noqa: E402
from aiwb.companion.server import PATH, CompanionServer  # noqa: E402
from aiwb.companion.service import CompanionError, CompanionService, DeviceRegistry  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402

VECTORS = Path(__file__).resolve().parents[3] / "packages/contracts/vectors/companion-envelope.v1.json"


class Phone:
    """Minimal client mirroring the Android implementation."""

    def __init__(self, svc: CompanionService, uri: str) -> None:
        _, self.host, self.port, self.pid, secret = uri.split(":")
        self.secret = crypto.b64d(secret)
        self.svc = svc
        self.key = os.urandom(32)
        self.device_id = ""

    def call(self, kid: str, key: bytes, req: dict, *, raw: bool = False):
        env = crypto.seal(key, kid, req, ts=int(self.svc.clock()))
        code, out = self.svc.handle(json.dumps(env).encode())
        if raw or code != 200:
            return code, out
        assert out["re"] == env["nonce"]
        return code, crypto.open_json(key, out, now=self.svc.clock())

    def pair(self):
        return self.call(self.pid, self.secret, {"op": "pair_request", "device_name": "Pixel 9",
                                                  "device_key": crypto.b64e(self.key)})

    def req(self, op: str, **kw):
        return self.call(self.device_id, self.key, {"op": op, **kw})


class EnvelopeTests(unittest.TestCase):
    def test_vectors(self):
        doc = json.loads(VECTORS.read_text(encoding="utf-8"))
        for c in doc["cases"]:
            master = crypto.b64d(c["master_key_b64url"])
            env = c["envelope"]
            again = crypto.seal_bytes(master, env["kid"], c["plaintext"].encode("utf-8"), ts=env["ts"],
                                      nonce=crypto.b64d(env["nonce"]), reply_to=env["re"])
            self.assertEqual(again, env)
            self.assertEqual(crypto.open_bytes(master, env, now=env["ts"]).decode("utf-8"), c["plaintext"])

    def test_tamper_wrong_key_expiry(self):
        k = os.urandom(32)
        env = crypto.seal(k, "dev-x", {"a": 1}, ts=1000)
        with self.assertRaises(crypto.EnvelopeError):
            crypto.open_json(os.urandom(32), env, now=1000)
        bad = dict(env, ct=env["ct"][:-2] + ("A" if env["ct"][-2] != "A" else "B") + env["ct"][-1])
        with self.assertRaises(crypto.EnvelopeError):
            crypto.open_json(k, bad, now=1000)
        with self.assertRaises(crypto.EnvelopeError):
            crypto.open_json(k, dict(env, kid="dev-y"), now=1000)
        with self.assertRaises(crypto.EnvelopeError):
            crypto.open_json(k, env, now=1000 + 301)
        with self.assertRaises(crypto.EnvelopeError):
            crypto.check_shape({**env, "extra": 1})
        self.assertEqual(crypto.open_json(k, env, now=1000), {"a": 1})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "proj").mkdir()
        self.ctl = ProjectsController(root / "proj")
        self.now = [1_792_300_000.0]
        self.reg = DeviceRegistry(root / "appdata" / "companion_devices.json")
        self.changes = []
        self.svc = CompanionService(self.reg, controller=lambda: self.ctl, clock=lambda: self.now[0],
                                    builds=lambda: [{"run_id": 7, "outcome": "success", "commit_sha": "f" * 40}],
                                    on_change=lambda: self.changes.append(1))

    def tearDown(self):
        self.tmp.cleanup()

    def paired(self, perms=("view_project",)) -> Phone:
        ph = Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        self.assertEqual(ph.pair()[1], {"ok": True, "status": "pending"})
        self.assertEqual(ph.call(ph.pid, ph.secret, {"op": "pair_status"})[1]["status"], "pending")
        [req] = self.svc.pending_requests()
        self.assertEqual(req["device_name"], "Pixel 9")
        dev = self.svc.decide(req["pairing_id"], True, perms)
        self.assertNotIn("key", dev)
        st = ph.call(ph.pid, ph.secret, {"op": "pair_status"})[1]
        self.assertEqual(st["status"], "approved")
        ph.device_id = st["device_id"]
        return ph

    def test_pairing_requires_desktop_approval_and_code_is_single_use(self):
        ph = Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        ph.pair()
        self.assertEqual(ph.pair()[1]["error"], "pairing_used")
        self.svc.decide(ph.pid, False)
        self.assertEqual(ph.call(ph.pid, ph.secret, {"op": "pair_status"})[1]["status"], "denied")
        self.assertEqual(self.reg.list(), [])
        ph2 = Phone(self.svc, self.svc.start_pairing("127.0.0.1", 1))
        self.now[0] += 601
        self.assertEqual(ph2.pair(), (403, {"error": "pairing_expired"}))
        with self.assertRaises(CompanionError):
            self.svc.decide("pair-nope", True)

    def test_read_only_default_and_permissions(self):
        ph = self.paired()
        t = self.ctl.project.tasks.create({"title": "Core", "objective": "c"})
        _, out = ph.req("get_state")
        self.assertTrue(out["ok"])
        self.assertEqual(out["snapshot"]["project_id"], self.ctl.project.store.load()["project_id"])
        self.assertEqual([x["task_id"] for x in out["tasks"]], [t["task_id"]])
        self.assertEqual(out["builds"][0]["run_id"], 7)
        self.assertNotIn(str(self.ctl.root), json.dumps(out), "no local paths")
        rev = self.ctl.project.store.revision
        self.assertEqual(ph.req("create_task", title="X", objective="y")[1]["error"], "forbidden")
        self.assertEqual(ph.req("submit_response", text="hi")[1]["error"], "forbidden")
        self.assertEqual(ph.req("apply_preview")[1]["error"], "bad_op", "no Apply/Run path exists")
        self.assertEqual(self.ctl.project.store.revision, rev, "refused requests change nothing")
        self.reg.set_permissions(ph.device_id, ["view_project", "create_task", "submit_response"])
        _, c = ph.req("create_task", title="From phone", objective="o")
        self.assertTrue(c["ok"])
        self.assertEqual(self.ctl.project.tasks.get(c["task_id"])["origin"], "companion")
        _, s = ph.req("submit_response", text="just text")
        self.assertEqual(s["kind"], "inbox_only")
        with self.assertRaises(CompanionError):
            self.reg.set_permissions(ph.device_id, ["run_command"])

    def test_revoke_replay_and_wrong_device(self):
        ph = self.paired()
        env = crypto.seal(ph.key, ph.device_id, {"op": "hello"}, ts=int(self.now[0]))
        self.assertEqual(self.svc.handle(json.dumps(env).encode())[0], 200)
        self.assertEqual(self.svc.handle(json.dumps(env).encode()), (401, {"error": "unauthenticated"}), "replay")
        forged = crypto.seal(os.urandom(32), ph.device_id, {"op": "hello"}, ts=int(self.now[0]))
        self.assertEqual(self.svc.handle(json.dumps(forged).encode())[0], 401)
        self.assertEqual(self.svc.handle(b"not json"), (400, {"error": "bad_request"}))
        self.reg.revoke(ph.device_id)
        self.assertEqual(ph.req("hello"), (403, {"error": "device_not_paired"}))
        [d] = self.reg.list()
        self.assertEqual((d["status"], d["permissions"]), ("revoked", []))
        self.assertNotIn("key", d)

    def test_no_project_open(self):
        ph = self.paired()
        self.ctl = None
        self.assertEqual(ph.req("hello")[1]["project"], False)
        self.assertEqual(ph.req("get_state")[1]["error"], "no_project")


class HttpTests(ServiceTests):
    def test_real_lan_endpoint(self):
        srv = CompanionServer(self.svc, host="127.0.0.1", port=0)
        port = srv.start()
        try:
            ph = self.paired()

            def post(path, body):
                r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST",
                                           headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(r, timeout=5) as resp:
                        return resp.status, json.loads(resp.read())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read())

            env = crypto.seal(ph.key, ph.device_id, {"op": "get_state"}, ts=int(self.now[0]))
            code, out = post(PATH, json.dumps(env).encode())
            self.assertEqual(code, 200)
            self.assertTrue(crypto.open_json(ph.key, out, now=self.now[0])["ok"])
            self.assertEqual(post("/other", b"{}")[0], 404)
            self.assertEqual(post(PATH, b"x" * 10)[0], 400)
        finally:
            srv.stop()
        self.assertFalse(srv.running)


if __name__ == "__main__":
    unittest.main()
