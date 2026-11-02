"""Optional helper AI (roadmap 5.19.0, R6). No Tk here: the HTTP client, the settings and the prompts.

Workbench talks to the user's chat AIs only through copy and paste. The helper AI is an *optional* small model behind
any OpenAI-compatible Chat Completions API (OpenRouter, Groq, Google AI Studio's OpenAI endpoint, a local Ollama …)
that the user configures in Settings. It does two things, each only when the user clicks:

* **Fix with helper AI** — an answer Workbench could not use is rewritten into the exact format it reads (files +
  AIWB_HANDOFF, or a manager proposal). The result goes back into the paste box; the user presses "Use this answer"
  and it takes the normal parse path. Nothing is applied by the helper itself.
* **Explain this step** — one or two plain sentences about what to do now.

Without settings nothing changes and nothing is sent anywhere. The API key is kept in Windows Credential Manager
(reference ``helper-ai:<uuid>`` in settings.json, never the key itself). Calls run in a background thread with a time
limit; errors become one clear sentence (and never contain the key).
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable

SETTINGS_KEY = "helper_ai"
DEFAULT_TIMEOUT = 60
MIN_TIMEOUT, MAX_TIMEOUT = 5, 300
MAX_ANSWER_CHARS = 60000          # what is sent of a pasted answer (the rest is cut, and the helper is told so)
MAX_REPLY_CHARS = 200000
USER_AGENT = "AI-Workbench-HelperAI"

# Addresses the user can pick from (any OpenAI-compatible address can be typed instead).
PRESETS = (
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("Groq", "https://api.groq.com/openai/v1"),
    ("Google AI Studio", "https://generativelanguage.googleapis.com/v1beta/openai"),
    ("Ollama (this computer)", "http://localhost:11434/v1"),
)


class HelperAIError(RuntimeError):
    """A helper AI call failed; the message is one sentence, safe to show (never contains the key)."""


# ---------------------------------------------------------------------------------------------------------- client
def normalize_base_url(url: str) -> str:
    u = str(url or "").strip().rstrip("/")
    for tail in ("/chat/completions", "/completions"):
        if u.endswith(tail):
            u = u[: -len(tail)].rstrip("/")
    if not (u.startswith("https://") or u.startswith("http://")) or len(u) < 10 or any(c.isspace() for c in u):
        raise HelperAIError("The helper AI address must start with https:// (or http:// for a local server).")
    return u


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def chat(base_url: str, model: str, messages: list[dict[str, str]], *, api_key: str = "",
         timeout: float = DEFAULT_TIMEOUT, opener: Callable[..., Any] | None = None) -> str:
    """One Chat Completions call; returns the reply text or raises :class:`HelperAIError`."""
    url = normalize_base_url(base_url) + "/chat/completions"
    if not str(model or "").strip():
        raise HelperAIError("Choose a helper AI model in Settings first.")
    body = json.dumps({"model": str(model).strip(), "messages": messages, "temperature": 0.2}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    open_ = opener or urllib.request.urlopen
    try:
        with open_(req, timeout=timeout) as resp:
            raw = resp.read(MAX_REPLY_CHARS * 4 + 1)
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code in (401, 403):
            raise HelperAIError(f"The helper AI refused the API key (HTTP {code}). Check the key in Settings.") from None
        if code == 404:
            raise HelperAIError("The helper AI address or model was not found (HTTP 404). Check both in Settings.") \
                from None
        if code == 429:
            raise HelperAIError("The helper AI is busy or the free limit is used up (HTTP 429). Try again later.") \
                from None
        raise HelperAIError(f"The helper AI answered with an error (HTTP {code}).") from None
    except (socket.timeout, TimeoutError):
        raise HelperAIError(f"The helper AI did not answer within {int(timeout)} seconds.") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise HelperAIError(f"The helper AI did not answer within {int(timeout)} seconds.") from None
        raise HelperAIError("The helper AI could not be reached. Check the address and your internet connection.") \
            from None
    except OSError:
        raise HelperAIError("The helper AI could not be reached. Check the address and your internet connection.") \
            from None
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise HelperAIError("The helper AI sent an answer Workbench cannot read (not a Chat Completions reply).") \
            from None
    if isinstance(content, list):   # some servers return content parts
        content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        raise HelperAIError("The helper AI sent an empty answer.")
    return _redact(content, api_key)[:MAX_REPLY_CHARS]


# --------------------------------------------------------------------------------------------------------- prompts
FORMAT_GUIDE = """Formats AI Workbench reads (use exactly these markers):

1. Files — one block per file, the complete file, body inside a fence of FOUR backticks:
<<<AIWB_FILE path="relative/path.ext" action="write">>>
````
(the complete file)
````
<<<AIWB_END_FILE>>>

2. After the files of a task answer, exactly one manifest block (valid JSON). Keep handoff_id, task_id,
task_revision and attempt_id exactly as they appear in the answer:
<<<AIWB_HANDOFF>>>
{"schema_version": "1.0", "handoff_id": "...", "task_id": "...", "task_revision": 1, "attempt_id": "...",
 "outcome": "complete|partial|blocked|needs_decision|failed", "summary": "...", "completed_items": [],
 "unresolved_items": [], "assumptions": [], "decision_requests": [], "validation_claims": [],
 "recommended_next_action": "..."}
<<<AIWB_END_HANDOFF>>>

3. A project manager's plan change (no files in it), valid JSON with at least one operation:
<<<AIWB_MANAGER_PROPOSAL>>>
{"schema_version": "1.0", "base_state_revision": <number from the answer>, "summary": "...",
 "operations": [{"operation": "create_task|update_task|add_dependency|remove_dependency|assign_agent|
 propose_decision|report_risk", ...}]}
<<<AIWB_END_MANAGER_PROPOSAL>>>"""

EXPECTED = {
    "handoff": "files (format 1) followed by one AIWB_HANDOFF manifest (format 2)",
    "manager": "one AIWB_MANAGER_PROPOSAL block (format 3)",
    "files": "files (format 1)",
}


def expected_for(step_key: str) -> str:
    """What the answer of a guided step should contain (a hint for the helper)."""
    k = str(step_key or "")
    if k.startswith("handoff:") or k in ("continue", "quick"):
        return EXPECTED["handoff"]
    if k in ("manager_update", "plan", "team"):
        return EXPECTED["manager"]
    return ""


def fix_messages(answer: str, problem: str = "", expected: str = "") -> list[dict[str, str]]:
    text = str(answer or "")
    cut = len(text) > MAX_ANSWER_CHARS
    text = text[:MAX_ANSWER_CHARS]
    system = ("You convert an AI chat answer into the exact format AI Workbench reads. Never invent anything: keep "
              "every file, every line of code and every statement of the answer; change only the shape. Do not add "
              "explanations. Output only the converted answer.")
    parts = [FORMAT_GUIDE, ""]
    if expected:
        parts.append(f"Workbench expects here: {expected}.")
    if problem:
        parts.append(f"Workbench reported: {str(problem)[:1500]}")
    if cut:
        parts.append("The answer below was cut to its first part; convert only what is there.")
    parts += ["", "The answer to convert:", "-----", text, "-----"]
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(parts)}]


def explain_messages(step: dict[str, Any], lang: str = "en") -> list[dict[str, str]]:
    language = "Persian (Farsi)" if lang == "fa" else "English"
    actions = ", ".join(str(a) for a in step.get("actions", []) if a)[:600]
    lines = [f"Step: {step.get('title', '')}"]
    if step.get("explain"):
        lines.append(f"Details: {str(step['explain'])[:1500]}")
    if actions:
        lines.append(f"Buttons the user can press: {actions}")
    system = (f"You help a non-expert use the desktop app AI Workbench. In {language}, explain in one or two short, "
              "plain sentences what the user should do now and why. No lists, no markdown.")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}]


# --------------------------------------------------------------------------------------------------------- service
class HelperService:
    """Settings (``settings[SETTINGS_KEY]``) + key (credential store) + calls. ``save()`` persists settings.

    ``settings`` may be the dict itself or a callable returning the *current* dict (the app replaces its settings dict
    on every save, so it passes ``lambda: self.settings_data``)."""

    def __init__(self, settings: dict[str, Any] | Callable[[], dict[str, Any]], save: Callable[[], Any] | None = None,
                 store: Any = None, *, opener: Callable[..., Any] | None = None) -> None:
        self._settings, self._save, self.store, self._opener = settings, save, store, opener

    @property
    def settings(self) -> dict[str, Any]:
        return self._settings() if callable(self._settings) else self._settings

    # -- settings
    @property
    def config(self) -> dict[str, Any]:
        c = self.settings.get(SETTINGS_KEY)
        return c if isinstance(c, dict) else {}

    @property
    def configured(self) -> bool:
        c = self.config
        return bool(str(c.get("base_url", "")).strip() and str(c.get("model", "")).strip())

    @property
    def timeout(self) -> int:
        try:
            t = int(self.config.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            t = DEFAULT_TIMEOUT
        return max(MIN_TIMEOUT, min(MAX_TIMEOUT, t))

    @property
    def has_key(self) -> bool:
        return bool(self.config.get("credential_ref"))

    def summary(self) -> str:
        if not self.configured:
            return "Not set up — Workbench works exactly as before."
        c = self.config
        return f"{c['model']} at {c['base_url']}" + (" · key saved" if self.has_key else " · no key")

    def configure(self, base_url: str, model: str, api_key: str | None = None, timeout: int | None = None) -> None:
        """Save the address and model; ``api_key``: None keeps the saved key, "" removes it, text replaces it."""
        url = normalize_base_url(base_url)
        model = str(model or "").strip()
        if not model:
            raise HelperAIError("Enter the model name (for example the one your provider lists).")
        c = dict(self.config)
        c.update(base_url=url, model=model)
        if timeout is not None:
            c["timeout"] = max(MIN_TIMEOUT, min(MAX_TIMEOUT, int(timeout)))
        if api_key is not None:
            key = api_key.strip()
            ref = str(c.get("credential_ref") or "")
            if key:
                if self.store is None:
                    raise HelperAIError("No secure key storage is available on this computer.")
                ref = ref or "helper-ai:" + str(uuid.uuid4())
                self._secret("set", ref, key)
                c["credential_ref"] = ref
            elif ref:
                self._secret("delete", ref)
                c.pop("credential_ref", None)
        self.settings[SETTINGS_KEY] = c
        if self._save is not None:
            self._save()

    def clear(self) -> None:
        ref = str(self.config.get("credential_ref") or "")
        if ref:
            try:
                self._secret("delete", ref)
            except HelperAIError:
                pass
        self.settings.pop(SETTINGS_KEY, None)
        if self._save is not None:
            self._save()

    def _secret(self, op: str, ref: str, value: str = "") -> str:
        try:
            if op == "set":
                self.store.set_secret(ref, value)
                return ""
            if op == "delete":
                self.store.delete_secret(ref)
                return ""
            return self.store.get_secret(ref)
        except HelperAIError:
            raise
        except Exception as exc:  # noqa: BLE001 - credential store errors are already UI-safe sentences
            raise HelperAIError(f"The helper AI key could not be {'saved' if op == 'set' else 'read'}: "
                                f"{str(exc)[:200]}") from None

    def api_key(self) -> str:
        ref = str(self.config.get("credential_ref") or "")
        return self._secret("get", ref) if ref and self.store is not None else ""

    # -- calls (blocking: run them through run_async from the UI)
    def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.configured:
            raise HelperAIError("The helper AI is not set up (Settings › Helper AI).")
        c = self.config
        return chat(c["base_url"], c["model"], messages, api_key=self.api_key(), timeout=self.timeout,
                    opener=self._opener)

    def test(self) -> str:
        return self.complete([{"role": "user", "content": "Reply with the single word OK."}])

    def fix_answer(self, answer: str, problem: str = "", expected: str = "") -> str:
        return strip_outer_fence(self.complete(fix_messages(answer, problem, expected)))

    def explain_step(self, step: dict[str, Any], lang: str = "en") -> str:
        return " ".join(self.complete(explain_messages(step, lang)).split())[:800]


def strip_outer_fence(text: str) -> str:
    """Small models often wrap the whole reply in one ``` fence; Workbench's own blocks must not be inside it."""
    t = text.strip()
    if t.startswith("```") and t.endswith("```") and "<<<AIWB_" in t:
        first = t.find("\n")
        inner = t[first + 1: -3] if first != -1 else t
        if not inner.lstrip().startswith("````"):
            return inner.strip() + "\n"
    return t + "\n"


def run_async(fn: Callable[[], Any], done: Callable[[Any, str], None],
              schedule: Callable[[Callable[[], None]], Any]) -> threading.Thread:
    """Run ``fn`` in a daemon thread; ``done(result, error)`` is handed to ``schedule`` (Tk: ``after(0, …)``)."""
    def work() -> None:
        try:
            result, error = fn(), ""
        except HelperAIError as exc:
            result, error = None, str(exc)
        except Exception as exc:  # noqa: BLE001 - never a traceback in the UI
            result, error = None, f"The helper AI call failed: {type(exc).__name__}."
        schedule(lambda: done(result, error))
    t = threading.Thread(target=work, name="helper-ai", daemon=True)
    t.start()
    return t
