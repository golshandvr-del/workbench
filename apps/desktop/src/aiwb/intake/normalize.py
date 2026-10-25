"""Normalize model output copied from chat UIs before any parser sees it (roadmap 3.2.0, P7).

Copying an answer out of ChatGPT / Gemini / Claude regularly injects artefacts that
break strict parsers even though the *content* is fine:

* BOM, NBSP / narrow NBSP, zero-width characters, CR/CRLF line endings;
* "smart" quotes around JSON keys/values and around AIWB header attributes;
* Markdown escapes of our own markers (``\\<\\<\\<AIWB\\_FILE ...\\>\\>\\>``);
* HTML entities (``&lt;&lt;&lt;AIWB_FILE``) when copied from rendered HTML;
* one outer Markdown fence around the whole answer;
* 5.12.0 (owner audit B1): a *rendered* answer selected and copied on Windows (not with the code block's Copy
  button) ends every line outside code fences with ``\\`` (a Markdown hard line break) and escapes ``_ * [ ]``;
* JSON with ``//`` / ``/* */`` comments, trailing commas or Python literals.

``normalize`` is *conservative*: it only touches structural lines (AIWB headers / end
markers, the outer fence) and, for JSON, only characters outside string literals —
file *bodies* inside AIWB blocks are never rewritten except for line endings and
invisible characters that cannot legitimately appear in source text. Callers always
try the raw text first and fall back to the normalized text, so a response that
parsed before can never be broken by this layer.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
NBSP = "\u00a0\u202f\u2007"
SMART_DOUBLE = "\u201c\u201d\u201e\u201f\u2033\u00ab\u00bb"
SMART_SINGLE = "\u2018\u2019\u201a\u201b\u2032"

_MARKER_WORDS = r"AIWB_(?:FILE|COMMAND|END_FILE|END_COMMAND|CONTEXT_REQUEST|END_CONTEXT_REQUEST|DELETE|RENAME|MOVE)"
# A line that, once escapes/entities are removed, is an AIWB marker.
_STRUCTURAL = re.compile(r"^\s*(?:\\?<|&lt;|&#60;|‹|＜){3}\s*\\?" + _MARKER_WORDS.replace("_", r"\\?_"))
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})([^\r\n`]*)$")


@dataclass
class NormalizeResult:
    text: str
    fixes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.fixes)


def _strip_invisible(s: str, fixes: list[str]) -> str:
    out = s
    if out.startswith("\ufeff"):
        out = out.lstrip("\ufeff")
        fixes.append("bom")
    zw = sum(out.count(c) for c in ZERO_WIDTH)
    if zw:
        out = out.translate({ord(c): None for c in ZERO_WIDTH})
        fixes.append(f"zero_width:{zw}")
    nb = sum(out.count(c) for c in NBSP)
    if nb:
        out = out.translate({ord(c): " " for c in NBSP})
        fixes.append(f"nbsp:{nb}")
    if "\r" in out:
        out = out.replace("\r\n", "\n").replace("\r", "\n")
        fixes.append("line_endings")
    return out


_FENCE_LOOSE = re.compile(r"^\s*(`{3,}|~{3,})([^\r\n`]*?)\\?\s*$")
_MD_ESCAPE = re.compile(r"(?<!\\)\\([_*\[\]#`>|~-])")
COPY_DAMAGE_RATIO = 0.6
COPY_DAMAGE_MIN_LINES = 3


def _regions(lines: list[str]) -> list[bool]:
    """``True`` for lines inside a code fence (fence lines included). A fence closes on the same fence string."""
    inside, opener, out = False, "", []
    for line in lines:
        m = _FENCE_LOOSE.match(line)
        if m and not inside:
            inside, opener = True, m.group(1)
            out.append(True)
        elif m and inside and m.group(1) == opener and not m.group(2).strip():
            inside = False
            out.append(True)
        else:
            out.append(inside)
    return out


def _damaged_ending(lines: list[str], idx: list[int]) -> str:
    """The character (``\\`` or ``/``) that ends most of the given lines, if it is copy damage; else ``""``."""
    body = [i for i in idx if lines[i].strip()]
    if len(body) < COPY_DAMAGE_MIN_LINES:
        return ""
    for ch in ("\\", "/"):
        hits = sum(1 for i in body if lines[i].rstrip().endswith(ch) and not lines[i].rstrip().endswith(ch * 3))
        if hits >= COPY_DAMAGE_MIN_LINES and hits / len(body) >= COPY_DAMAGE_RATIO:
            return ch
    return ""


def strip_copy_damage(text: str, fixes: list[str] | None = None) -> str:
    """Undo what selecting a rendered chat answer and copying it does (5.12.0, owner audit B1).

    * When most non-empty lines **outside** code fences end with ``\\`` (or ``/``) — lines such as ``{`` and
      ``}`` never legitimately do — exactly that one character is removed from every line that has it. A fenced
      block is repaired the same way only when it is damaged as much as the text around it.
    * Markdown escapes (``\\_ \\* \\[ \\] \\# \\` \\>``) outside fences and outside AIWB file bodies are
      removed: they are never part of JSON, of our markers or of prose.

    Conservative: text that is not damaged comes back unchanged (``fixes`` untouched).
    """
    fixes = [] if fixes is None else fixes
    s = str(text or "")
    if "\\" not in s and "/" not in s:
        return s
    lines = s.split("\n")
    fenced = _regions(lines)
    outside = [i for i, f in enumerate(lines) if not fenced[i]]
    ch = _damaged_ending(lines, outside)
    n_end = 0
    if ch:
        targets = set(outside)
        # fenced blocks: repair a block only when it is itself damaged like the text around it
        i = 0
        while i < len(lines):
            if fenced[i]:
                j = i
                while j + 1 < len(lines) and fenced[j + 1] and not (j > i and _FENCE_LOOSE.match(lines[j])):
                    j += 1
                inner = list(range(i + 1, j))
                if _damaged_ending(lines, inner) == ch:
                    targets.update(inner)
                targets.update({i, j})  # the fence lines themselves may carry the damage
                i = j + 1
            else:
                i += 1
        for i in sorted(targets):
            r = lines[i].rstrip()
            if r.endswith(ch):
                lines[i] = r[:-1].rstrip() if r[:-1].strip() else ""
                n_end += 1
        fenced = _regions(lines)
    n_esc = 0
    in_file = False
    for i, line in enumerate(lines):
        probe = line.strip()
        if re.match(r"^<<<AIWB_FILE\b", probe.replace("\\", "")):
            in_file = True
        if fenced[i] or (in_file and not probe.replace("\\", "").startswith("<<<AIWB")):
            pass
        elif "\\" in line:
            new, k = _MD_ESCAPE.subn(r"\1", line)
            if k:
                lines[i], n_esc = new, n_esc + k
        if re.match(r"^<<<AIWB_END_FILE>>>", lines[i].strip()):
            in_file = False
    if n_end:
        name = "backslashes" if ch == "\\" else "slashes"
        fixes.append(f"copy_damage:{n_end} line-end {name} removed (answer was copied as rendered text)")
    if n_esc:
        fixes.append(f"markdown_escapes:{n_esc} removed")
    return "\n".join(lines) if (n_end or n_esc) else s


def _fix_marker_line(line: str) -> str:
    s = line.strip()
    s = html.unescape(s)
    s = s.replace("\\<", "<").replace("\\>", ">").replace("\\_", "_").replace("\\=", "=").replace('\\"', '"')
    s = s.replace("‹", "<").replace("›", ">").replace("＜", "<").replace("＞", ">")
    s = s.translate({ord(c): '"' for c in SMART_DOUBLE})
    s = s.translate({ord(c): "'" for c in SMART_SINGLE})
    s = re.sub(r"^(?:\*\*|__|`)+|(?:\*\*|__|`)+$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"<<<\s+", "<<<", s)
    s = re.sub(r"\s+>>>$", ">>>", s)
    s = re.sub(r'\s*=\s*"', '="', s)
    return s


def _fix_structural_lines(s: str, fixes: list[str]) -> str:
    lines = s.split("\n")
    n = 0
    for i, line in enumerate(lines):
        probe = re.sub(r"^\s*(?:\*\*|__|`)+", "", line)
        if _STRUCTURAL.match(probe) or (("AIWB" in probe) and probe.lstrip().startswith(("<<<", "&lt;", "\\<"))):
            fixed = _fix_marker_line(line)
            if fixed != line:
                lines[i] = fixed
                n += 1
    if n:
        fixes.append(f"marker_lines:{n}")
    return "\n".join(lines)


def _unwrap_outer_fence(s: str, fixes: list[str]) -> str:
    """Drop a fence that wraps AIWB blocks (the whole answer, or blocks after some prose).

    Only a fence whose first non-empty inner line is an AIWB header, and whose matching
    closing fence comes right after an AIWB end marker, is removed. Fences *inside*
    file bodies are never touched because they never start with an AIWB header.
    """
    lines = s.split("\n")
    out: list[str] = []
    i, removed = 0, 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and re.match(r"^\s*<<<AIWB_(?:FILE|COMMAND)\b", lines[j]):
                fence = m.group(1)
                close = None
                for k in range(len(lines) - 1, j, -1):
                    if lines[k].strip() == fence:
                        prev = k - 1
                        while prev > j and not lines[prev].strip():
                            prev -= 1
                        if re.match(r"^\s*<<<AIWB_END_(?:FILE|COMMAND)>>>\s*$", lines[prev]):
                            close = k
                        break
                if close is not None:
                    out.extend(lines[i + 1:close])
                    removed += 1
                    i = close + 1
                    continue
        out.append(lines[i])
        i += 1
    if not removed:
        return s
    fixes.append("outer_fence")
    return "\n".join(out)


def normalize(text: str | bytes) -> NormalizeResult:
    """Return a cleaned copy of *text* plus the list of fixes applied (empty → unchanged)."""
    s = text.decode("utf-8", errors="replace") if isinstance(text, (bytes, bytearray)) else str(text or "")
    fixes: list[str] = []
    s = _strip_invisible(s, fixes)
    s = strip_copy_damage(s, fixes)
    s = _fix_structural_lines(s, fixes)
    s = _unwrap_outer_fence(s, fixes)
    if _looks_jsonish(s):
        js = normalize_json_text(s)
        if js.changed:
            s = js.text
            fixes.extend(js.fixes)
    return NormalizeResult(s, fixes)


# --------------------------------------------------------------------------- JSON

def _looks_jsonish(s: str) -> bool:
    if re.search(r"(?m)^\s*<<<AIWB_(?:FILE|COMMAND)\b", s):
        return False
    t = s.strip()
    return t.startswith("{") or bool(re.search(r"(?im)^\s*`{3,}\s*json\b", t)) or bool(
        re.search(r"[\"“”']protocol[\"“”']\s*:", t))


def _json_body(s: str) -> tuple[str, str, str]:
    """Split prose/fence around the JSON object: (prefix, body, suffix)."""
    m = re.search(r"(?ims)^\s*(`{3,}|~{3,})\s*json[^\n]*\n(.*?)(?:^\s*\1\s*$|\Z)", s)
    if m:
        return s[:m.start(2)], m.group(2), s[m.end(2):]
    a = s.find("{")
    if a < 0:
        return s, "", ""
    b = s.rfind("}")
    if b < a:
        return s[:a], s[a:], ""
    return s[:a], s[a:b + 1], s[b + 1:]


def _scan_json(body: str, fixes: list[str]) -> str:
    """Single pass outside/inside strings: smart quotes, comments, trailing commas, literals."""
    out: list[str] = []
    i, n = 0, len(body)
    in_str = False
    quote_fix = comment_fix = comma_fix = literal_fix = 0
    while i < n:
        c = body[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                out.append(body[i:i + 2]); i += 2; continue
            if c == '"':
                in_str = False; out.append(c); i += 1; continue
            if c in "\u201c\u201d":
                # A smart quote closing a string that was opened by a smart quote.
                nxt = body[i + 1:i + 40].lstrip()
                if nxt[:1] in (":", ",", "}", "]", ""):
                    in_str = False; out.append('"'); quote_fix += 1; i += 1; continue
            if c == "\n":
                out.append("\\n"); i += 1; continue
            out.append(c); i += 1; continue
        if c == '"' or c in "\u201c\u201d\u201e":
            if c != '"':
                quote_fix += 1
            in_str = True; out.append('"'); i += 1; continue
        if c == "/" and body[i + 1:i + 2] == "/":
            j = body.find("\n", i)
            i = n if j < 0 else j
            comment_fix += 1; continue
        if c == "/" and body[i + 1:i + 2] == "*":
            j = body.find("*/", i + 2)
            i = n if j < 0 else j + 2
            comment_fix += 1; continue
        if c == ",":
            k = i + 1
            while k < n and body[k] in " \t\n":
                k += 1
            if k < n and body[k] in "}]":
                comma_fix += 1; i += 1; continue
        if c.isalpha():
            m = re.match(r"(True|False|None|undefined)\b", body[i:])
            if m:
                out.append({"True": "true", "False": "false", "None": "null", "undefined": "null"}[m.group(1)])
                literal_fix += 1; i += len(m.group(1)); continue
        out.append(c); i += 1
    for name, k in (("json_smart_quotes", quote_fix), ("json_comments", comment_fix),
                    ("json_trailing_commas", comma_fix), ("json_literals", literal_fix)):
        if k:
            fixes.append(f"{name}:{k}")
    return "".join(out)


def normalize_json_text(text: str) -> NormalizeResult:
    """Repair a JSON answer only if it does not already parse."""
    s = str(text or "")
    prefix, body, suffix = _json_body(s)
    if not body.strip():
        return NormalizeResult(s)
    try:
        json.loads(body)
        return NormalizeResult(s)
    except (json.JSONDecodeError, ValueError):
        pass
    fixes: list[str] = []
    candidate = body
    if "\\_" in candidate or "\\*" in candidate:
        # Markdown-escaped underscores/asterisks outside of real JSON escapes.
        c2 = re.sub(r"\\([_*\[\]#])", r"\1", candidate)
        if c2 != candidate:
            candidate = c2; fixes.append("markdown_escapes")
    if "&quot;" in candidate or "&lt;" in candidate or "&amp;" in candidate:
        candidate = html.unescape(candidate); fixes.append("html_entities")
    candidate = _scan_json(candidate, fixes)
    try:
        json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return NormalizeResult(s)  # do not hand a half-repaired object to the parser
    return NormalizeResult(prefix + candidate + suffix, fixes)


# --------------------------------------------------------------------- truncation

@dataclass
class TruncationReport:
    truncated: bool
    reason: str = ""
    last_complete_path: str = ""
    open_path: str = ""
    completed_paths: list[str] = field(default_factory=list)


def truncation_report(text: str) -> TruncationReport:
    """Detect an answer that was cut off (chat length limit / stopped generation)."""
    s = normalize(text).text.rstrip()
    if not s:
        return TruncationReport(False)
    heads = list(re.finditer(r'(?m)^\s*<<<AIWB_(FILE|COMMAND)\b([^\n]*)>>>\s*$', s))
    if heads:
        done: list[str] = []
        open_path = ""
        for i, h in enumerate(heads):
            stop = heads[i + 1].start() if i + 1 < len(heads) else len(s)
            seg = s[h.end():stop]
            pm = re.search(r'(?:path|id)="([^"]*)"', h.group(2))
            name = pm.group(1) if pm else "?"
            if re.search(r"(?m)^\s*<<<AIWB_END_(?:FILE|COMMAND)>>>\s*$", seg):
                done.append(name)
            elif i == len(heads) - 1:
                open_path = name
        if open_path:
            return TruncationReport(True, "unclosed_block", done[-1] if done else "", open_path, done)
        return TruncationReport(False, completed_paths=done)
    if len(re.findall(r"(?m)^\s*(?:`{3,}|~{3,})", s)) % 2 == 1:
        return TruncationReport(True, "unclosed_fence")
    _p, body, _s = _json_body(s)
    b = body.strip()
    if b.startswith("{"):
        try:
            json.loads(normalize_json_text(b).text)
        except json.JSONDecodeError as exc:
            depth = 0
            in_str = esc = False
            for ch in b:
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch in "{[":
                    depth += 1
                elif ch in "}]":
                    depth -= 1
            if depth > 0 or in_str or exc.pos >= len(b) - 1:
                paths = re.findall(r'"path"\s*:\s*"([^"]+)"', b)
                return TruncationReport(True, "json_cut", paths[-2] if len(paths) > 1 else "",
                                        paths[-1] if paths else "", paths[:-1])
    return TruncationReport(False)


def continue_prompt(report: TruncationReport, *, attempt_id: str = "") -> str:
    """Prompt that asks the model to continue exactly where the answer was cut off."""
    att = f" (attempt {attempt_id})" if attempt_id else ""
    lines = [f"Your previous answer{att} was cut off before it finished."]
    if report.reason == "unclosed_block":
        if report.completed_paths:
            lines.append("These files arrived complete — do NOT resend them: " + ", ".join(report.completed_paths) + ".")
        lines.append(f'Resend the file "{report.open_path}" from its <<<AIWB_FILE ...>>> header, completely, '
                     "then continue with every remaining file and action.")
    elif report.reason == "json_cut":
        lines.append("The JSON object is incomplete. Do not continue mid-object: resend the response using "
                     "AIWB blocks (one <<<AIWB_FILE path=\"...\" action=\"write\">>> ... <<<AIWB_END_FILE>>> per file), "
                     "skipping files that were already complete" +
                     (": " + ", ".join(report.completed_paths) if report.completed_paths else "") + ".")
    else:
        lines.append("Resend the rest of the answer starting from the last complete block.")
    lines += [
        "Rules: plain text only, no outer Markdown fence around the whole answer, each marker on its own line,",
        "end every file with <<<AIWB_END_FILE>>>. If the answer would be long, split it and say \"PART 1 of N\".",
    ]
    return "\n".join(lines)
