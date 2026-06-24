"""LaTeX cleaning utility to strip document structure."""

import re


def clean_latex(text):
    """Strip LaTeX document structure, keep renderable content."""
    if not text:
        return text
    
    # Remove document class and packages
    text = re.sub(r'\\documentclass[^\n]*\n', '', text)
    text = re.sub(r'\\usepackage[^\n]*\n', '', text)
    text = re.sub(r'\\geometry[^\n]*\n', '', text)
    
    # Remove document environment tags
    text = text.replace('\\begin{document}', '')
    text = text.replace('\\end{document}', '')
    
    # Convert section/subsection to markdown-style headers
    text = re.sub(r'\\section\*\{([^}]+)\}', r'## \1', text)
    text = re.sub(r'\\subsection\*\{([^}]+)\}', r'### \1', text)
    
    # Fix common AI-generated LaTeX typos
    # \$$Xpt] should be \\[Xpt] (line break with spacing)
    text = text.replace('\\$$6pt]', '\\[6pt]')
    text = text.replace('\\$$4pt]', '\\[4pt]')
    text = text.replace('\\$$8pt]', '\\[8pt]')
    text = text.replace('\\$$12pt]', '\\[12pt]')
    
    # Convert \\[...\\] to $$...$$ (display math)
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    
    # Convert \\begin{align*}...\\end{align*} to KaTeX-compatible format
    def convert_align(match):
        content = match.group(1)
        return '$$\\begin{aligned}' + content + '\\end{aligned}$$'
    
    text = re.sub(
        r'\\begin\{align\*\}(.+?)\\end\{align\*\}',
        convert_align,
        text,
        flags=re.DOTALL
    )
    
    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    
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
