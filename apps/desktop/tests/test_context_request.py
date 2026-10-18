"""Tests for roadmap 1.16.3: AIWB_CONTEXT_REQUEST parse/resolve/pack and Inbox routing."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import AI_Workbench as wb  # noqa: E402
from aiwb import context_request as cr  # noqa: E402
from aiwb import inbox  # noqa: E402


def req_text(files, **extra):
    data = {"schema_version": "1.0", "type": "AIWB_CONTEXT_REQUEST", "attempt_id": "att-x", "reason": "need it",
            "files": files, **extra}
    return "<<<AIWB_CONTEXT_REQUEST>>>\n" + json.dumps(data) + "\n<<<AIWB_END_CONTEXT_REQUEST>>>\n"


def path_problem_for(root):
    def f(p):
        try:
            wb.validate_relative_path(root, p)
            return ""
        except wb.WorkbenchError as exc:
            return str(exc)
    return f


class ParseTests(unittest.TestCase):
    def test_block_and_json(self):
        r = cr.parse_request(req_text([{"path": "a.py"}]))
        self.assertEqual(r.items[0].mode, "full_file")
        r2 = cr.parse_request(json.dumps({"schema_version": "1.0", "type": "AIWB_CONTEXT_REQUEST", "questions": ["q"]}))
        self.assertEqual(r2.questions, ["q"])

    def test_rejects(self):
        for bad in ("no block", req_text([]), req_text([{"path": "a", "mode": "range"}]),
                    req_text([{"path": "a", "mode": "symbol", "symbol": "1x"}]),
                    req_text([{"path": "a", "mode": "weird"}]),
                    "<<<AIWB_CONTEXT_REQUEST>>>{bad<<<AIWB_END_CONTEXT_REQUEST>>>"):
            with self.assertRaises(cr.ContextRequestError):
                cr.parse_request(bad)
        with self.assertRaises(cr.ContextRequestError):
            cr.parse_request(req_text([{"path": "a"}], schema_version="2.0"))

    def test_free_text_hints(self):
        self.assertIn("src/app.py", cr.free_text_hints("Please send me the file `src/app.py` so I can fix it."))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "m.py").write_text("import os\n\nclass A:\n    @staticmethod\n    def f():\n        return 1\n\ndef g():\n    pass\n", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, files, **kw):
        r = cr.parse_request(req_text(files, **kw))
        return r, cr.resolve(r, self.root, path_problem=path_problem_for(self.root), is_sensitive=wb.is_sensitive_path)

    def test_modes_and_statuses(self):
        _, items = self.resolve([
            {"path": "m.py"}, {"path": "m.py", "mode": "range", "ranges": [{"start_line": 3, "end_line": 4}]},
            {"path": "m.py", "mode": "symbol", "symbol": "A.f"}, {"path": "m.py", "mode": "symbol", "symbol": "nope"},
            {"path": "missing.py"}, {"path": "../x.py"}, {"path": ".env"},
            {"path": "m.py", "mode": "range", "ranges": [{"start_line": 50, "end_line": 60}]}])
        st = [i.status for i in items]
        self.assertEqual(st, ["ready", "ready", "ready", "symbol_not_found", "missing", "refused_unsafe",
                              "refused_sensitive", "invalid_range"])
        self.assertEqual(items[2].lines, "4-6")  # decorator included
        self.assertNotIn("secret", "".join(i.content for i in items))

    def test_sensitive_allowed_explicitly(self):
        r = cr.parse_request(req_text([{"path": ".env"}]))
        items = cr.resolve(r, self.root, path_problem=path_problem_for(self.root), is_sensitive=wb.is_sensitive_path,
                           allow_sensitive={".env"})
        self.assertEqual(items[0].status, "ready")

    def test_stale_hash(self):
        _, items = self.resolve([{"path": "m.py"}], base_hashes={"m.py": "0" * 64})
        self.assertEqual(items[0].status, "stale")
        self.assertTrue(items[0].deliverable)

    def test_packs(self):
        r, items = self.resolve([{"path": "m.py"}, {"path": "m.py", "mode": "symbol", "symbol": "g"}, {"path": "nope.py"}],
                                questions=["why?"])
        text = cr.pack_inline(r, items, attempt_line="AIWB_ATTEMPT_ID: att-1")
        self.assertTrue(text.startswith("AIWB_ATTEMPT_ID: att-1"))
        self.assertIn("## Not provided", text)
        self.assertIn("nope.py: missing", text)
        self.assertIn("why?", text)
        zf = zipfile.ZipFile(io.BytesIO(cr.pack_zip(r, items, self.root)))
        names = zf.namelist()
        self.assertIn("context/m.py", names)
        self.assertIn("AIWB_CONTEXT_MANIFEST.json", names)
        man = json.loads(zf.read("AIWB_CONTEXT_MANIFEST.json"))
        self.assertEqual(len(man["files"]), 3)
        self.assertEqual(zf.read("context/m.py"), (self.root / "m.py").read_bytes())

    def test_capability_line_in_manifest(self):
        self.assertIn("AIWB_CONTEXT_REQUEST", wb.build_capability_manifest(self.root))


class InboxRoutingTests(unittest.TestCase):
    def test_context_request_is_not_an_import_error(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pipe = wb.make_inbox_pipeline(root)
            cap = pipe.capture_text(req_text([{"path": "a.py"}]), source="test")
            out = pipe.process(cap.response.response_id)
            self.assertEqual(out.status, "context_request")
            self.assertEqual([i.code for i in out.issues if i.code == "context_request"], ["context_request"])
            self.assertFalse(out.changes)
            self.assertIn("AIWB_CONTEXT_REQUEST", inbox.explain(out.issues[0].to_dict()))


if __name__ == "__main__":
    unittest.main()
