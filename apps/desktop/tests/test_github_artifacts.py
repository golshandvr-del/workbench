"""Tests for aiwb.github.artifacts (v1.14.7 dispatch + safe artifact download)."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.github import artifacts as ar  # noqa: E402
from aiwb.github.actions import GitHubActionsService, WorkflowInfo, WorkflowRun  # noqa: E402
from aiwb.github.api_client import GitHubApiClient, GitHubApiError, HttpResponse  # noqa: E402

TOKEN = "github_pat_" + "A" * 40
SHA = "a" * 40
OTHER = "b" * 40

WF_TEXT = """
name: Build
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      channel:
        description: "Release channel"   # comment
        type: choice
        required: true
        options: [beta, stable]
      dry_run:
        type: boolean
        default: true
      count:
        type: number
        required: false
      note:
        description: |
          multi line
          text
jobs:
  build:
    runs-on: ubuntu-latest
"""


def wf(active: bool = True) -> WorkflowInfo:
    return WorkflowInfo(7, "Build", ".github/workflows/build.yml", "active" if active else "disabled_manually", "", ("push", "workflow_dispatch"))


def run(run_id: int = 50, sha: str = SHA) -> WorkflowRun:
    return WorkflowRun(run_id, 7, "Build", "push", "completed", "success", "main", sha, 1, 1, "2026-10-17T10:00:00Z", "", "", "")


def get_client(responses: dict[str, HttpResponse]) -> GitHubApiClient:
    def transport(url: str, headers: dict, timeout: float) -> HttpResponse:
        for key, resp in responses.items():
            if key in url:
                return resp
        return HttpResponse(404, {}, b"{}")
    return GitHubApiClient(transport=transport)


def j(value: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, json.dumps(value).encode())


def make_zip(entries: list[tuple[str, bytes]], *, mode: int | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo(name)
            info.filename = name  # keep raw name (ZipInfo() turns '\\' into '/' on Windows)
            info.compress_type = zipfile.ZIP_DEFLATED
            if mode is not None:
                info.external_attr = mode << 16
            zf.writestr(info, data)
    return buf.getvalue()


class InputParsingTests(unittest.TestCase):
    def test_inputs_types_options_defaults(self) -> None:
        form = ar.parse_dispatch_inputs(WF_TEXT)
        self.assertTrue(form.dispatchable, form.error)
        by = {i.name: i for i in form.inputs}
        self.assertEqual(by["channel"].type, "choice")
        self.assertEqual(by["channel"].options, ("beta", "stable"))
        self.assertTrue(by["channel"].required)
        self.assertEqual(by["dry_run"].default, "true")
        self.assertEqual(by["count"].type, "number")
        self.assertEqual(by["note"].type, "string")
        self.assertEqual(by["channel"].description, "Release channel")

    def test_not_dispatchable_forms(self) -> None:
        self.assertFalse(ar.parse_dispatch_inputs("on: push\n").dispatchable)
        self.assertFalse(ar.parse_dispatch_inputs("on:\n  push:\n").dispatchable)
        self.assertTrue(ar.parse_dispatch_inputs("on: [push, workflow_dispatch]\n").dispatchable)
        self.assertTrue(ar.parse_dispatch_inputs("on:\n  workflow_dispatch:\n").dispatchable)
        bad = ar.parse_dispatch_inputs("on:\n  workflow_dispatch:\n    inputs:\n      x:\n        type: weird\n")
        self.assertFalse(bad.dispatchable)
        self.assertIn("unsupported type", bad.error)

    def test_validation(self) -> None:
        inputs = ar.parse_dispatch_inputs(WF_TEXT).inputs
        with self.assertRaisesRegex(ValueError, "required"):
            ar.validate_dispatch_values(inputs, {})
        with self.assertRaisesRegex(ValueError, "one of"):
            ar.validate_dispatch_values(inputs, {"channel": "nightly"})
        with self.assertRaisesRegex(ValueError, "number"):
            ar.validate_dispatch_values(inputs, {"channel": "beta", "count": "ten"})
        with self.assertRaisesRegex(ValueError, "true or false"):
            ar.validate_dispatch_values(inputs, {"channel": "beta", "dry_run": "maybe"})
        with self.assertRaisesRegex(ValueError, "Unknown"):
            ar.validate_dispatch_values(inputs, {"channel": "beta", "evil": "1"})
        ok = ar.validate_dispatch_values(inputs, {"channel": "stable", "dry_run": False, "count": "3"})
        self.assertEqual(ok, {"channel": "stable", "dry_run": "false", "count": "3"})
        self.assertEqual(ar.validate_dispatch_values(inputs, {"channel": "beta"})["dry_run"], "true")

    def test_ref_validation(self) -> None:
        for good in ("main", "feat/x", "desktop-v1.14.7"):
            self.assertEqual(ar.validate_ref(good), good)
        for bad in ("", "a..b", "/x", "x/", "a b", "x.lock", "a~1", "-"[:0]):
            with self.assertRaises(ValueError):
                ar.validate_ref(bad)


class DispatchTests(unittest.TestCase):
    def svc(self, status: int, body: object = None, runs: list[dict] | None = None, clock: float = 1_792_000_000.0) -> tuple[ar.GitHubDispatchService, list]:
        calls: list = []

        def request(url: str, method: str, headers: dict, data: bytes | None, timeout: float) -> HttpResponse:
            calls.append((url, method, headers, data))
            return HttpResponse(status, {}, json.dumps(body).encode() if body is not None else b"")
        client = get_client({"/runs": j({"workflow_runs": runs or []})})
        return ar.GitHubDispatchService(GitHubActionsService(client), request=request, clock=lambda: clock), calls

    def test_204_is_unconfirmed_not_success(self) -> None:
        svc, calls = self.svc(204)
        form = ar.parse_dispatch_inputs(WF_TEXT)
        res = svc.dispatch(TOKEN, "o", "r", wf(), ref="main", inputs={"channel": "beta"}, form=form)
        self.assertEqual(res.state, "unconfirmed")
        self.assertIsNone(res.run_id)
        url, method, headers, data = calls[0]
        self.assertTrue(url.endswith("/actions/workflows/7/dispatches"))
        self.assertEqual(method, "POST")
        body = json.loads(data)
        self.assertEqual(body["ref"], "main")
        self.assertEqual(body["inputs"]["channel"], "beta")

    def test_200_with_run_id_is_confirmed(self) -> None:
        svc, _ = self.svc(200, {"workflow_run_id": 999, "html_url": "https://github.com/o/r/actions/runs/999"})
        res = svc.dispatch(TOKEN, "o", "r", wf(), ref="main", inputs={"channel": "beta"}, form=ar.parse_dispatch_inputs(WF_TEXT))
        self.assertEqual((res.state, res.run_id), ("confirmed", 999))

    def test_refuses_non_dispatchable_and_disabled(self) -> None:
        svc, calls = self.svc(204)
        with self.assertRaises(GitHubApiError):
            svc.dispatch(TOKEN, "o", "r", wf(), ref="main", inputs={}, form=ar.DispatchForm(False))
        with self.assertRaises(GitHubApiError):
            svc.dispatch(TOKEN, "o", "r", wf(active=False), ref="main", inputs={}, form=ar.DispatchForm(True))
        self.assertEqual(calls, [])

    def test_errors_categorized(self) -> None:
        for status, cat in ((401, "authentication"), (403, "permission_or_policy"), (422, "request"), (500, "server")):
            svc, _ = self.svc(status)
            with self.assertRaises(GitHubApiError) as cm:
                svc.dispatch(TOKEN, "o", "r", wf(), ref="main", inputs={}, form=ar.DispatchForm(True))
            self.assertEqual(cm.exception.category, cat)

    def test_strict_run_matching(self) -> None:
        now = 1_792_000_000.0
        iso = lambda t: __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(t))
        mk = lambda i, ev="workflow_dispatch", br="main", t=now + 5: {"id": i, "workflow_id": 7, "event": ev, "status": "queued", "head_branch": br, "head_sha": SHA, "created_at": iso(t)}
        pending = ar.DispatchResult("unconfirmed", 7, "main", now)
        # one new candidate (others: wrong event, wrong branch, too old, already known)
        runs = [mk(1), mk(2, ev="push"), mk(3, br="dev"), mk(4, t=now - 3600), mk(5)]
        svc, _ = self.svc(204, runs=runs, clock=now)
        res = svc.find_dispatched_run(TOKEN, "o", "r", pending, known_run_ids={5})
        self.assertEqual((res.state, res.run_id), ("confirmed", 1))
        # two candidates -> ambiguous, not confirmed
        res2 = svc.find_dispatched_run(TOKEN, "o", "r", pending)
        self.assertEqual(res2.state, "unconfirmed")
        self.assertIn("cannot tell", res2.message)


class ArtifactTests(unittest.TestCase):
    def artifacts_payload(self, **over: object) -> dict:
        a = {"id": 11, "name": "setup", "size_in_bytes": 0, "expired": False, "expires_at": "2026-12-01T00:00:00Z",
             "created_at": "2026-10-17T10:00:00Z", "digest": "", "workflow_run": {"id": 50, "head_sha": SHA, "head_branch": "main", "repository_id": 3}}
        a.update(over)
        return {"artifacts": [a]}

    def service(self, zip_bytes: bytes, *, payload: dict | None = None, zip_status: int = 302, location: str = "https://pipelines.actions.githubusercontent.com/x?sig=SECRET") -> ar.GitHubDispatchService:
        client = get_client({"/artifacts?": j(payload or self.artifacts_payload())})
        self.sent: list = []

        def request(url: str, method: str, headers: dict, data: bytes | None, timeout: float) -> HttpResponse:
            return HttpResponse(zip_status, {"Location": location} if zip_status in (302,) else {}, b"")

        def stream(url: str, timeout: float):
            self.sent.append(url)
            yield zip_bytes[:10]
            yield zip_bytes[10:]
        return ar.GitHubDispatchService(GitHubActionsService(client), request=request, stream=stream)

    def test_list_and_match(self) -> None:
        svc = self.service(b"")
        (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
        self.assertEqual((a.artifact_id, a.run_id, a.head_sha, a.repository_id), (11, 50, SHA, 3))
        self.assertTrue(ar.artifact_matches(a, run_id=50, head_sha=SHA))
        self.assertFalse(ar.artifact_matches(a, run_id=51, head_sha=SHA))
        self.assertFalse(ar.artifact_matches(a, run_id=50, head_sha=OTHER))
        self.assertFalse(ar.artifact_matches(a, run_id=50, head_sha=SHA, repository_id=4))

    def test_download_hash_computed_only_vs_matched(self) -> None:
        data = make_zip([("a.txt", b"hello")])
        with tempfile.TemporaryDirectory() as d:
            svc = self.service(data, payload=self.artifacts_payload(size_in_bytes=len(data)))
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            res = svc.download_artifact(TOKEN, "o", "r", a, Path(d), run=run())
            self.assertEqual(res.verification, "computed_only")
            self.assertFalse(res.verified)
            self.assertEqual(res.sha256, hashlib.sha256(data).hexdigest())
            self.assertTrue(res.path.is_file())
            self.assertEqual(self.sent, ["https://pipelines.actions.githubusercontent.com/x?sig=SECRET"])
            self.assertNotIn("SECRET", repr(res))
        with tempfile.TemporaryDirectory() as d:
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            svc = self.service(data, payload=self.artifacts_payload(size_in_bytes=len(data), digest=digest))
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            self.assertTrue(svc.download_artifact(TOKEN, "o", "r", a, Path(d)).verified)

    def test_digest_mismatch_removes_file(self) -> None:
        data = make_zip([("a.txt", b"hello")])
        with tempfile.TemporaryDirectory() as d:
            svc = self.service(data, payload=self.artifacts_payload(digest="sha256:" + "0" * 64))
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            with self.assertRaises(GitHubApiError) as cm:
                svc.download_artifact(TOKEN, "o", "r", a, Path(d))
            self.assertEqual(cm.exception.category, "integrity")
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_refusals(self) -> None:
        data = make_zip([("a.txt", b"x")])
        with tempfile.TemporaryDirectory() as d:
            svc = self.service(data, payload=self.artifacts_payload(expired=True))
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            self.assertFalse(a.downloadable)
            with self.assertRaises(GitHubApiError) as cm:
                svc.download_artifact(TOKEN, "o", "r", a, Path(d))
            self.assertEqual(cm.exception.category, "expired")
            svc = self.service(data)
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            with self.assertRaisesRegex(GitHubApiError, "does not belong"):
                svc.download_artifact(TOKEN, "o", "r", a, Path(d), run=run(sha=OTHER))
            svc = self.service(data, zip_status=410)
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            with self.assertRaises(GitHubApiError) as cm:
                svc.download_artifact(TOKEN, "o", "r", a, Path(d))
            self.assertEqual(cm.exception.category, "expired")
            svc = self.service(data, location="https://evil.example.com/x")
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            with self.assertRaises(GitHubApiError) as cm:
                svc.download_artifact(TOKEN, "o", "r", a, Path(d))
            self.assertNotIn("evil", str(cm.exception))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_size_cap_and_partial_cleanup(self) -> None:
        data = make_zip([("a.txt", b"y" * 5000)])
        with tempfile.TemporaryDirectory() as d:
            svc = self.service(data)
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            with self.assertRaises(GitHubApiError) as cm:
                svc.download_artifact(TOKEN, "o", "r", a, Path(d), max_bytes=20)
            self.assertEqual(cm.exception.category, "too_large")
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_stream_failure_hides_url(self) -> None:
        client = get_client({"/artifacts?": j(self.artifacts_payload())})

        def request(*a: object) -> HttpResponse:
            return HttpResponse(302, {"location": "https://x.blob.core.windows.net/a?sig=TOPSECRET"}, b"")

        def stream(url: str, timeout: float):
            yield b"PK"
            raise OSError(f"connection reset for {url}")
        svc = ar.GitHubDispatchService(GitHubActionsService(client), request=request, stream=stream)
        with tempfile.TemporaryDirectory() as d:
            (a,) = svc.list_artifacts(TOKEN, "o", "r", 50)
            with self.assertRaises(GitHubApiError) as cm:
                svc.download_artifact(TOKEN, "o", "r", a, Path(d))
            self.assertNotIn("TOPSECRET", str(cm.exception))
            self.assertIsNone(cm.exception.__cause__)
            self.assertEqual(list(Path(d).iterdir()), [])


class SafeExtractTests(unittest.TestCase):
    def extract(self, data: bytes, **limits: object) -> list[Path]:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        zp = Path(self.tmp.name) / "a.zip"
        zp.write_bytes(data)
        return ar.safe_extract_zip(zp, Path(self.tmp.name) / "out", ar.ExtractLimits(**limits))  # type: ignore[arg-type]

    def assertRejected(self, data: bytes, pattern: str, **limits: object) -> None:
        with self.assertRaisesRegex(ar.UnsafeArchiveError, pattern):
            self.extract(data, **limits)
        self.assertFalse((Path(self.tmp.name) / "out").exists())
        self.assertEqual([p.name for p in Path(self.tmp.name).iterdir()], ["a.zip"])

    def test_ok(self) -> None:
        out = self.extract(make_zip([("dir/a.txt", b"1"), ("b.bin", b"2")]))
        self.assertEqual(sorted(p.name for p in out), ["a.txt", "b.bin"])
        self.assertEqual((Path(self.tmp.name) / "out" / "dir" / "a.txt").read_bytes(), b"1")

    def test_traversal_absolute_backslash(self) -> None:
        self.assertRejected(make_zip([("../evil.txt", b"x")]), "escapes")
        self.assertRejected(make_zip([("a/../../evil.txt", b"x")]), "escapes")
        self.assertRejected(make_zip([("/etc/passwd", b"x")]), "absolute")
        self.assertRejected(make_zip([("C:/x.txt", b"x")]), "absolute")
        self.assertRejected(make_zip([("a\\..\\x.txt", b"x")]), "backslash")

    def test_duplicates_case_collision_windows_names(self) -> None:
        self.assertRejected(make_zip([("A.txt", b"1"), ("a.TXT", b"2")]), "case-colliding")
        self.assertRejected(make_zip([("aux.txt", b"1")]), "reserved")
        self.assertRejected(make_zip([("bad:name.txt", b"1")]), "invalid on Windows")
        self.assertRejected(make_zip([("trail. ", b"1")]), "invalid on Windows")
        self.assertRejected(make_zip([("a", b"1"), ("a/b", b"2")]), "both a file and a folder")

    def test_special_files(self) -> None:
        self.assertRejected(make_zip([("link", b"target")], mode=stat.S_IFLNK | 0o777), "link or special")

    def test_limits_and_bomb(self) -> None:
        self.assertRejected(make_zip([(f"f{i}", b"") for i in range(5)]), "too many", max_entries=4)
        self.assertRejected(make_zip([("big", b"\0" * 3 * 1024 * 1024)]), "compression ratio")
        self.assertRejected(make_zip([("a", b"x" * 100), ("b", b"x" * 100)]), "beyond the allowed", max_total_bytes=150, max_ratio=1e9)

    def test_forged_header_size(self) -> None:
        data = bytearray(make_zip([("a.txt", b"z" * 4000)]))
        # forge uncompressed size in the central directory to 10 bytes
        cd = data.rfind(b"PK\x01\x02")
        data[cd + 24:cd + 28] = (10).to_bytes(4, "little")
        lh = data.find(b"PK\x03\x04")
        data[lh + 22:lh + 26] = (10).to_bytes(4, "little")
        with self.assertRaises((ar.UnsafeArchiveError, zipfile.BadZipFile)):
            self.extract(bytes(data), max_ratio=1e9)
        self.assertFalse((Path(self.tmp.name) / "out").exists())

    def test_existing_dest_refused_and_not_zip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            zp = Path(d) / "a.zip"
            zp.write_bytes(make_zip([("a", b"1")]))
            (Path(d) / "out").mkdir()
            with self.assertRaisesRegex(ar.UnsafeArchiveError, "already exists"):
                ar.safe_extract_zip(zp, Path(d) / "out")
            zp.write_bytes(b"not a zip")
            with self.assertRaisesRegex(ar.UnsafeArchiveError, "Not a valid ZIP"):
                ar.safe_extract_zip(zp, Path(d) / "new")

    def test_sanitize_filename(self) -> None:
        self.assertEqual(ar.sanitize_filename("con.zip"), "_con.zip")
        self.assertEqual(ar.sanitize_filename("a/b:c.zip"), "a_b_c.zip")


if __name__ == "__main__":
    unittest.main()
