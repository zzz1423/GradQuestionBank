"""
LaTeX post-processing: wrap bare LaTeX commands in $...$ delimiters.
"""
from __future__ import annotations
import re

# CJK character ranges (expression boundaries)
_CJK = re.compile("[\u2E80-\u2FFF\u3000-\u303F\u4E00-\u9FFF\uFF00-\uFF60]")

# Non-math punctuation (expression boundaries)
_PUNCT = re.compile("[,;:!?.,\u3001\u3002\uFF0C\uFF0E\uFF1B\uFF1A\uFF01\uFF1F]")

# Existing inline/display math
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)", re.DOTALL)
_DISPLAY_MATH = re.compile(r"\$\$.+?\$\$", re.DOTALL)

# Bare LaTeX command (backslash + letters)
_CMD = re.compile(r"\\[a-zA-Z]+")


def normalize_latex_in_text(text: str) -> str:
    if not text or "\\" not in text:
        return text

    # Protect existing $...$ and $$...$$ regions
    protected = set()
    for m in _DISPLAY_MATH.finditer(text):
        protected.update(range(m.start(), m.end()))
    for m in _INLINE_MATH.finditer(text):
        protected.update(range(m.start(), m.end()))

    # Find bare commands
    bare = [m for m in _CMD.finditer(text) if not any(i in protected for i in range(m.start(), m.end()))]
    if not bare:
        return text

    # Group into segments separated by CJK/punctuation
    segs = []
    cs = bare[0].start()
    ce = bare[0].end()
    for b in bare[1:]:
        gap = text[ce:b.start()]
        if any(_CJK.match(c) or _PUNCT.match(c) or c in "\n\r" for c in gap):
            segs.append((cs, ce))
            cs = b.start()
            ce = b.end()
        else:
            ce = max(ce, b.end())
    segs.append((cs, ce))

    # Extend each segment to cover trailing math
    segs = [(s, _extend(text, e)) for s, e in segs]

    # Wrap segments in $...$
    parts = []
    prev = 0
    for s, e in segs:
        parts.append(text[prev:s])
        parts.append("$" + text[s:e] + "$")
        prev = e
    parts.append(text[prev:])
    return "".join(parts)


def _extend(text: str, pos: int) -> int:
    """Extend past trailing braces, ^, _, operators, digits, letters, closing braces."""
    n = len(text)
    i = pos
    while i < n:
        while i < n and text[i] == " ":
            i += 1
        if i >= n:
            break
        ch = text[i]
        # Opening brace - consume balanced pair
        if ch == "{":
            d = 1; i += 1
            while i < n and d > 0:
                if text[i] == "{": d += 1
                elif text[i] == "}": d -= 1
                i += 1
            continue
        # Closing brace - closes a brace opened before the segment
        if ch == "}":
            i += 1
            continue
        # Subscript/superscript
        if ch in "^_":
            i += 1
            if i < n and text[i] == "{":
                d = 1; i += 1
                while i < n and d > 0:
                    if text[i] == "{": d += 1
                    elif text[i] == "}": d -= 1
                    i += 1
            elif i < n:
                i += 1
            continue
        # Parentheses
        if ch == "(":
            d = 1; i += 1
            while i < n and d > 0:
                if text[i] == "(": d += 1
                elif text[i] == ")": d -= 1
                i += 1
            continue
        # Closing paren - standalone
        if ch == ")":
            i += 1
            continue
        # Math operators and relations
        if ch in "+-=<>!":
            i += 1
            if i < n and text[i] in "=<>":
                i += 1
            continue
        # Digits and ASCII letters (math variables)
        if ch.isdigit() or (ch.isalpha() and ord(ch) < 0x2000):
            i += 1
            continue
        break
    return i
