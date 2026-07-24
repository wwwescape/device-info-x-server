"""Validates the constrained Markdown subset DIX AI insight text is allowed to use (see
`app/cli.py`'s `add_insight`, and the client's `parseInsightMarkup`) — Bold, Italics, Bold &
Italics, Links, URLs and Email Addresses, and Escaping Characters, each following
https://www.markdownguide.org/basic-syntax/'s own rules for that section, not a looser
reinterpretation.

This is the strict, reject-at-authoring-time counterpart to the client's lenient, never-fails
renderer — not a shared implementation of it. There's no shared runtime between this server and
the Kotlin client to actually share code, so both independently implement the same greedy,
priority-ordered scan (escape, then longest-delimiter-first emphasis, then links, then autolinks);
this one reports the first problem it finds instead of degrading to literal text the way the
client does.
"""

import re

_ESCAPABLE_CHARS = "\\`*_{}[]()#+-.!|"
_AUTOLINK_URL_RE = re.compile(r"^https?://\S+$")
_AUTOLINK_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_insight_markup(text: str) -> str | None:
    """None if `text`'s Markdown is well-formed; otherwise a human-readable description of the
    first problem found, suitable for printing straight to the CLI."""
    i = 0
    n = len(text)
    while i < n:
        c = text[i]

        if c == "\\":
            # A trailing lone backslash, or one before a character the guide doesn't list as
            # escapable, is left as a literal `\` — matches standard Markdown leniency rather
            # than treating every backslash as required-to-be-a-real-escape.
            i += 2 if i + 1 < n and text[i + 1] in _ESCAPABLE_CHARS else 1
            continue

        if c in "*_":
            run_len = _run_length(text, i, c)
            match = _find_emphasis_close(text, i, c, run_len)
            if match is not None:
                i = match
                continue
            opening_len = min(run_len, 3)
            content_start = i + opening_len
            if content_start < n and not text[content_start].isspace():
                delimiter = c * opening_len
                return f"{delimiter!r} is opened but never closed with a matching {delimiter!r} later in the text."
            i += run_len
            continue

        if c == "[":
            close_bracket = text.find("]", i + 1)
            if close_bracket == -1:
                return "Found a '[' that's never closed with ']'."
            if close_bracket + 1 >= n or text[close_bracket + 1] != "(":
                return "Found '[...]' with no '(' immediately after it to start the link's URL — e.g. [title](url)."
            close_paren = text.find(")", close_bracket + 2)
            if close_paren == -1:
                return "Found a link's opening '(' with no matching closing ')'."
            link_text = text[i + 1 : close_bracket]
            inside = text[close_bracket + 2 : close_paren].strip()
            url = inside.split(" ", 1)[0].strip()
            if not link_text or not url:
                return "Found a link with empty link text or an empty URL — e.g. [title](url)."
            i = close_paren + 1
            continue

        if c == "<":
            close_angle = text.find(">", i + 1)
            if close_angle == -1:
                return "Found a '<' that's never closed with '>'."
            inner = text[i + 1 : close_angle]
            if not inner or any(ch.isspace() for ch in inner) or not (
                _AUTOLINK_URL_RE.match(inner) or _AUTOLINK_EMAIL_RE.match(inner)
            ):
                return f"{inner!r} between '<' and '>' isn't a plain https:// URL or email address."
            i = close_angle + 1
            continue

        i += 1

    return None


def _run_length(text: str, start: int, c: str) -> int:
    end = start
    while end < len(text) and text[end] == c:
        end += 1
    return end - start


def _find_emphasis_close(text: str, start: int, c: str, run_len: int) -> int | None:
    """Tries the longest delimiter length first (3, then 2, then 1) — matches the client
    parser's own greedy precedence, so `***bold and italic***` resolves as one span rather than
    reporting a leftover `*`. Returns the index just past a valid closing delimiter, or None.

    A delimiter run immediately followed by whitespace (or the end of the text) is never treated
    as an opening delimiter at all, and a closing run immediately preceded by whitespace is never
    treated as a valid close — matches how real Markdown treats whitespace-flanked `*`/`_` as
    literal characters rather than emphasis. Without this, ordinary text like "5 * 3 = 15" would
    be misread as an opening delimiter with no close and rejected as broken syntax."""
    for length in range(min(run_len, 3), 0, -1):
        delimiter = c * length
        content_start = start + length
        if content_start >= len(text) or text[content_start].isspace():
            continue
        close_at = text.find(delimiter, content_start)
        if close_at <= content_start or text[close_at - 1].isspace():
            continue
        return close_at + length
    return None
