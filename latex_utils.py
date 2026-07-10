"""LaTeX cleaning utility to strip document structure and fix common issues."""

import re

def _match_braces(text, start):
    """Find the end position of a brace group starting at 'start'.
    Returns the index AFTER the closing brace, or -1 if not found."""
    if start >= len(text) or text[start] != '{':
        return -1
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _remove_brace_command(text, cmd_pattern):
    """Remove a LaTeX command and its brace-delimited argument, handling nested braces."""
    result = []
    i = 0
    while i < len(text):
        m = re.match(cmd_pattern, text[i:])
        if m:
            brace_start = i + m.end()
            brace_end = _match_braces(text, brace_start)
            if brace_end != -1:
                result.append(text[i:i])  # empty string before command
                i = brace_end
                continue
        result.append(text[i])
        i += 1
    return ''.join(result)


def _replace_brace_command(text, cmd_pattern, replacement_func):
    """Replace a LaTeX command and its brace-delimited argument, handling nested braces."""
    result = []
    i = 0
    while i < len(text):
        m = re.match(cmd_pattern, text[i:])
        if m:
            brace_start = i + m.end()
            brace_end = _match_braces(text, brace_start)
            if brace_end != -1:
                inner = text[brace_start+1:brace_end-1]
                result.append(replacement_func(inner))
                i = brace_end
                continue
        result.append(text[i])
        i += 1
    return ''.join(result)





def clean_latex(text):
    """Strip LaTeX document structure, keep renderable content for KaTeX."""
    if not text:
        return text

    # Remove HTML tags that might be mixed in (from previous KaTeX rendering)
    text = re.sub(r'<[^>]+>', '', text)

    # Remove document class and packages
    text = re.sub(r'\\documentclass[^\n]*\n', '', text)
    text = re.sub(r'\\usepackage[^\n]*\n', '', text)
    text = re.sub(r'\\geometry[^\n]*\n', '', text)

    # Remove document environment tags
    text = text.replace('\\begin{document}', '')
    text = text.replace('\\end{document}', '')

    # Remove section/subsection (unnumbered and numbered, handles nested braces)
    text = _remove_brace_command(text, r'\\section\*?\s*(?=\{)')
    text = _remove_brace_command(text, r'\\subsection\*?\s*(?=\{)')

    # Remove document-level formatting commands
    text = re.sub(r'\\noindent\*?', '', text)
    text = re.sub(r'\\textbf\{([^}]*)\}', r'**\1**', text)
    text = re.sub(r'\\textit\{([^}]*)\}', r'*\1*', text)
    text = re.sub(r'\\emph\{([^}]*)\}', r'*\1*', text)

    # Remove spacing commands
    text = re.sub(r'\\(bigskip|medskip|smallskip)\*?', '', text)

    # Fix common AI-generated LaTeX typos
    # \$$Xpt] should be \\[Xpt] (line break with spacing)
    for pt in ['4pt', '6pt', '8pt', '10pt', '12pt', '20pt']:
        text = text.replace('\\$' + pt + ']', '\\[' + pt + ']')

    # Convert \[...\] to $$...$$ (display math)
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)

    # Convert \begin{align*}...\end{align*} to KaTeX-compatible format
    def convert_align(match):
        content = match.group(1)
        return '$$\\begin{aligned}' + content + '\\end{aligned}$$'

    text = re.sub(
        r'\\begin\{align\*\}(.+?)\\end\{align\*\}',
        convert_align,
        text,
        flags=re.DOTALL
    )

    # Also handle standalone \begin{aligned}...\end{aligned} (wrap in $$ if not already)
    text = re.sub(
        r'(?<!\$)\\begin\{aligned\}(.+?)\\end\{aligned\}(?!\$)',
        r'$$\\begin{aligned}\1\\end{aligned}$$',
        text,
        flags=re.DOTALL
    )

    # Remove \qquad, \quad (spacing commands)
    text = text.replace('\\qquad', '  ')
    text = text.replace('\\quad', ' ')

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove leading/trailing whitespace on each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


def extract_latex_formulas(text):
    """Extract all LaTeX formulas from text for preview."""
    formulas = []

    # Find display math: $$...$$
    for match in re.finditer(r'\$\$(.+?)\$\$', text, re.DOTALL):
        formulas.append(('display', match.group(1).strip()))

    # Find inline math: $...$
    for match in re.finditer(r'\$([^$]+?)\$', text):
        formulas.append(('inline', match.group(1).strip()))

    return formulas


def generate_tags_from_kps(knowledge_points):
    """Generate tags automatically from knowledge points."""
    tags = []
    for kp in knowledge_points:
        name = kp.get('name', '')
        if name:
            tags.append(name)
    return list(set(tags))  # Deduplicate
