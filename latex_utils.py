"""LaTeX cleaning utility to strip document structure and fix common issues."""

import re


def clean_latex(text):
    """
    Clean LaTeX source into KaTeX-friendly renderable text.
    
    Parameters:
    	text: The LaTeX text to clean.
    
    Returns:
    	str: The cleaned text with document scaffolding removed, common formatting normalized, and display math converted for KaTeX.
    """
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

    # Remove section/subsection (unnumbered and numbered)
    text = re.sub(r'\\section\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\subsection\*?\{[^}]*\}', '', text)

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
        """
        Wrap an align environment in KaTeX-compatible display math.
        
        Parameters:
        	match: A regex match whose first group contains the align environment content.
        
        Returns:
        	str: The content wrapped as a display-math aligned block.
        """
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
    """
    Extract LaTeX display and inline formulas from text.
    
    Returns:
    	formulas (list[tuple[str, str]]): A list of ``("display", content)`` and ``("inline", content)`` tuples, where each formula content is stripped of surrounding whitespace.
    """
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
