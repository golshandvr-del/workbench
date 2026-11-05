"""Roadmap 5.19.0 gate: the optional helper AI against a local fake OpenAI-compatible server.

Success, timeout, 401, a broken reply, unreachable address; the key goes only in the Authorization header and is kept
in the credential store (settings.json holds only a reference); without settings nothing is configured; the fix
prompt carries the formats and never asks to invent; the async runner hands errors back as one sentence.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb import helper_ai as h  # noqa: E402
from aiwb.github.credential_store import CredentialStoreError, MemoryCredentialStore, _validate_ref  # noqa: E402

KEY = "sk-test-SECRET-123"


class FakeServer:
    """A tiny Chat Completions server; ``mode`` decides the reply, ``seen`` records the requests."""

    def __init__(self) -> None:
        self.mode = "ok"
        self.reply = "OK"
        self.seen: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a) -> None:  # quiet
                pass

            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                outer.seen.append({"path": self.path, "auth": self.headers.get("Authorization", ""),
                                   "body": json.loads(body or b"{}")})
                if outer.mode == "slow":
                    time.sleep(2.5)
                if outer.mode == "401":
                    self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"bad key"}'); return
                if outer.mode == "429":
                    self.send_response(429); self.end_headers(); return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if outer.mode == "broken":
                    self.wfile.write(b"<html>not json</html>")
                elif outer.mode == "empty":
                    self.wfile.write(json.dumps({"choices": [{"message": {"content": "  "}}]}).encode())
                else:
                    self.wfile.write(json.dumps({"choices": [{"message": {"role": "assistant",
                                                                          "content": outer.reply}}]}).encode())

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class HelperClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.srv = FakeServer()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.srv.close()

    def setUp(self) -> None:
        self.srv.mode, self.srv.reply = "ok", "OK"
        self.srv.seen.clear()
        self.settings: dict = {}
        self.saved = 0
        self.store = MemoryCredentialStore()
        self.svc = h.HelperService(self.settings, save=self._save, store=self.store)

    def _save(self) -> None:
        self.saved += 1

    def test_not_configured_by_default_and_nothing_sent(self) -> None:
        self.assertFalse(self.svc.configured)
        self.assertIn("works exactly as before", self.svc.summary())
        with self.assertRaises(h.HelperAIError):
            self.svc.complete([{"role": "user", "content": "x"}])
        self.assertEqual(self.srv.seen, [])

    def test_success_and_key_only_in_header_and_store(self) -> None:
        self.svc.configure(self.srv.url + "/chat/completions", "tiny-model", api_key=KEY, timeout=10)
        self.assertTrue(self.svc.configured)
        self.assertEqual(self.saved, 1)
        self.assertEqual(self.settings["helper_ai"]["base_url"], self.srv.url)
        ref = self.settings["helper_ai"]["credential_ref"]
        self.assertTrue(ref.startswith("helper-ai:"))
        self.assertNotIn(KEY, json.dumps(self.settings), "the key never goes to settings.json")
        self.assertEqual(self.store.get_secret(ref), KEY)
        self.assertEqual(self.svc.test(), "OK")
        req = self.srv.seen[-1]
        self.assertEqual(req["path"], "/v1/chat/completions")
        self.assertEqual(req["auth"], "Bearer " + KEY)
        self.assertEqual(req["body"]["model"], "tiny-model")
        self.assertIn("key saved", self.svc.summary())

    def test_no_key_for_local_servers(self) -> None:
        self.svc.configure(self.srv.url, "llama3.2")
        self.assertEqual(self.svc.test(), "OK")
        self.assertEqual(self.srv.seen[-1]["auth"], "")

    def test_timeout_is_one_sentence(self) -> None:
        self.srv.mode = "slow"
        with self.assertRaises(h.HelperAIError) as cm:
            h.chat(self.srv.url, "m", [{"role": "user", "content": "x"}], timeout=0.5)
        self.assertIn("did not answer within", str(cm.exception))

    def test_401_names_the_key_and_never_shows_it(self) -> None:
        self.srv.mode = "401"
        with self.assertRaises(h.HelperAIError) as cm:
            h.chat(self.srv.url, "m", [{"role": "user", "content": "x"}], api_key=KEY, timeout=5)
        self.assertIn("API key", str(cm.exception))
        self.assertNotIn(KEY, str(cm.exception))

    def test_429_and_broken_and_empty_replies(self) -> None:
        for mode, word in (("429", "limit"), ("broken", "cannot read"), ("empty", "empty")):
            self.srv.mode = mode
            with self.assertRaises(h.HelperAIError) as cm:
                h.chat(self.srv.url, "m", [{"role": "user", "content": "x"}], timeout=5)
            self.assertIn(word, str(cm.exception), mode)

    def test_unreachable_address(self) -> None:
        with self.assertRaises(h.HelperAIError) as cm:
            h.chat("http://127.0.0.1:9/v1", "m", [{"role": "user", "content": "x"}], timeout=3)
        self.assertIn("could not be reached", str(cm.exception))

    def test_bad_settings_are_refused(self) -> None:
        for url, model in (("ftp://x.y/v1", "m"), ("not a url", "m"), (self.srv.url, " ")):
            with self.assertRaises(h.HelperAIError):
                self.svc.configure(url, model)
        self.assertFalse(self.svc.configured)
        self.assertEqual(self.saved, 0)

    def test_key_replace_keep_remove_and_clear(self) -> None:
        self.svc.configure(self.srv.url, "m", api_key=KEY)
        ref = self.settings["helper_ai"]["credential_ref"]
        self.svc.configure(self.srv.url, "m2")                 # None keeps the key
        self.assertEqual(self.svc.api_key(), KEY)
        self.svc.configure(self.srv.url, "m2", api_key="new-key")
        self.assertEqual(self.settings["helper_ai"]["credential_ref"], ref, "same reference, new secret")
        self.assertEqual(self.svc.api_key(), "new-key")
        self.svc.configure(self.srv.url, "m2", api_key="")     # "" removes it
        self.assertFalse(self.svc.has_key)
        with self.assertRaises(CredentialStoreError):
            self.store.get_secret(ref)
        self.svc.configure(self.srv.url, "m2", api_key=KEY)
        ref2 = self.settings["helper_ai"]["credential_ref"]
        self.svc.clear()
        self.assertNotIn("helper_ai", self.settings)
        with self.assertRaises(CredentialStoreError):
            self.store.get_secret(ref2)

    def test_bf017_failed_settings_save_restores_config_and_secret(self) -> None:
        from copy import deepcopy
        for failure in (False, OSError("disk full")):
            for operation in ("initial", "replace", "keep", "remove_key", "clear"):
                with self.subTest(failure=failure, operation=operation):
                    settings = {"other": "untouched"}
                    store = MemoryCredentialStore()
                    svc = h.HelperService(settings, store=store)
                    if operation != "initial":
                        svc.configure(self.srv.url, "old-model", api_key=KEY)
                    before = deepcopy(settings)
                    secrets = dict(store._values)

                    def fail_save():
                        if isinstance(failure, Exception):
                            raise failure
                        return failure

                    svc._save = fail_save
                    with self.assertRaises(h.HelperAIError) as caught:
                        if operation == "clear":
                            svc.clear()
                        else:
                            key = {"initial": "new-key", "replace": "new-key", "keep": None,
                                   "remove_key": ""}[operation]
                            svc.configure(self.srv.url, "new-model", api_key=key)
                    self.assertIn("could not be saved", str(caught.exception))
                    self.assertNotIn(KEY, str(caught.exception))
                    self.assertEqual(settings, before)
                    self.assertEqual(store._values, secrets)

    def test_bf017_failed_key_deletion_keeps_reachable_configuration(self) -> None:
        from unittest.mock import patch
        self.svc.configure(self.srv.url, "m", api_key=KEY)
        before = dict(self.svc.config)
        with patch.object(self.store, "delete_secret", side_effect=CredentialStoreError("locked")):
            with self.assertRaises(h.HelperAIError):
                self.svc.clear()
        self.assertEqual(self.svc.config, before)
        self.assertEqual(self.svc.api_key(), KEY)

    def test_fix_answer_round_trip(self) -> None:
        self.srv.reply = ("```\n<<<AIWB_FILE path=\"index.html\" action=\"write\">>>\n````\n<p>hi</p>\n````\n"
                          "<<<AIWB_END_FILE>>>\n```")
        self.svc.configure(self.srv.url, "m")
        out = self.svc.fix_answer("Here is index.html:\n<p>hi</p>", "no files found", h.expected_for("handoff:H-1"))
        self.assertTrue(out.startswith("<<<AIWB_FILE"), out)
        prompt = self.srv.seen[-1]["body"]["messages"]
        self.assertIn("Never invent", prompt[0]["content"])
        self.assertIn("<<<AIWB_HANDOFF>>>", prompt[1]["content"])
        self.assertIn("no files found", prompt[1]["content"])
        self.assertIn("<p>hi</p>", prompt[1]["content"])

    def test_explain_step_is_short_and_in_the_language(self) -> None:
        self.srv.reply = "Copy the prompt.\n\nThen paste the answer."
        self.svc.configure(self.srv.url, "m")
        out = self.svc.explain_step({"title": "Send the prompt", "explain": "…", "actions": ["I sent it"]}, "fa")
        self.assertEqual(out, "Copy the prompt. Then paste the answer.")
        self.assertIn("Persian", self.srv.seen[-1]["body"]["messages"][0]["content"])

    def test_run_async_hands_back_result_and_error(self) -> None:
        got: list = []
        ev = threading.Event()

        def done(result, error) -> None:
            got.append((result, error))
            ev.set()
        h.run_async(lambda: 42, done, lambda f: f())
        ev.wait(5)
        ev.clear()

        def boom():
            raise h.HelperAIError("nope.")
        h.run_async(boom, done, lambda f: f())
        ev.wait(5)
        self.assertEqual(got, [(42, ""), (None, "nope.")])


class PureTests(unittest.TestCase):
    def test_credential_refs(self) -> None:
        import uuid
        u = str(uuid.uuid4())
        self.assertEqual(_validate_ref("helper-ai:" + u), "AIWorkbench/HelperAI/" + u)
        self.assertEqual(_validate_ref("github-api:" + u), "AIWorkbench/GitHub/API/" + u)
        for bad in ("helper-ai:x", "other:" + u, "helper-ai" + u):
            with self.assertRaises(CredentialStoreError):
                _validate_ref(bad)

    def test_long_answer_is_cut_and_said_so(self) -> None:
        msgs = h.fix_messages("x" * (h.MAX_ANSWER_CHARS + 50))
        self.assertIn("cut to its first part", msgs[1]["content"])
        self.assertLess(len(msgs[1]["content"]), h.MAX_ANSWER_CHARS + 4000)

    def test_expected_and_fence(self) -> None:
        self.assertIn("AIWB_HANDOFF", h.expected_for("handoff:H-0001"))
        self.assertIn("MANAGER_PROPOSAL", h.expected_for("manager_update"))
        self.assertEqual(h.expected_for("decide:D-1"), "")
        self.assertEqual(h.strip_outer_fence("plain"), "plain\n")


if __name__ == "__main__":
    unittest.main()
