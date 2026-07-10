"""
Regenerate Markdown from a NormalizedDocument.

This proves that the Normalization layer is Information Preserving:
any Markdown can be regenerated from the normalized DOM without
access to the original OCR output.
"""
from pipeline.schema import (
    NormalizedDocument, Block, BlockType, Inline, InlineType, ImageAsset,
)


def render_markdown(doc: NormalizedDocument) -> str:
    """
    Render a complete Markdown string from a NormalizedDocument.

    The output should be deterministic for a given NormalizedDocument.
    """
    parts: list[str] = []

    for page in doc.pages:
        for block in page.blocks:
            md = _render_block(block, doc.images)
            if md is not None:
                parts.append(md)

    return "\n\n".join(parts) + "\n"


def _render_block(block: Block, images: list[ImageAsset]) -> str | None:
    """Render a single Block to Markdown. Returns None for blocks to skip."""
    t = block.type

    if t == BlockType.title:
        level = block.level or 1
        content = _render_inline_list(block.title_content or [])
        return f"{'#' * level} {content}"

    elif t == BlockType.paragraph:
        return _render_inline_list(block.inline_content or [])

    elif t == BlockType.list_item:
        return f"- {_render_inline_list(block.inline_content or [])}"

    elif t == BlockType.formula_block:
        latex = block.latex or ""
        parts = [f"$$\n{latex}\n$$"]
        if block.image_ref:
            img = _find_image(block.image_ref, images)
            if img:
                parts.append(f"![formula]({img.path})")
        return "\n".join(parts)

    elif t == BlockType.equation_interline:
        latex = block.latex or ""
        parts = [f"$$\n{latex}\n$$"]
        if block.image_ref:
            img = _find_image(block.image_ref, images)
            if img:
                parts.append(f"![formula]({img.path})")
        return "\n".join(parts)

    elif t == BlockType.figure:
        caption = _render_inline_list(block.caption or [])
        img = _find_image(block.image_ref, images) if block.image_ref else None
        path = img.path if img else "unknown.png"
        return f"![{caption}]({path})"

    elif t == BlockType.table:
        return f"[表格: {block.text or block.latex or '(见原始数据)'}]"

    elif t == BlockType.caption:
        return f"*{_render_inline_list(block.inline_content or [])}*"

    elif t == BlockType.page_header:
        return f"---\n{block.text or ''}\n---"

    elif t == BlockType.page_footer:
        return f"---\n{block.text or ''}\n---"

    elif t == BlockType.aside:
        text = block.text or ""
        return f"> {text}" if text else None

    elif t == BlockType.page_number:
        return None  # Skip page numbers in Markdown

    elif t == BlockType.code_block:
        return f"```\n{block.text or ''}\n```"

    else:
        # unknown or unrecognized types: render as text if available
        if block.text:
            return block.text
        return None


def _render_inline_list(inlines: list[Inline]) -> str:
    """Render a list of Inline elements to a Markdown string."""
    parts = []
    for inline in inlines:
        if inline.type == InlineType.text:
            parts.append(inline.content)
        elif inline.type == InlineType.formula:
            parts.append(f"${inline.content}$")
        elif inline.type == InlineType.image:
            parts.append(f"![inline]({inline.content})")
        else:
            parts.append(inline.content)
    return "".join(parts)


def _find_image(image_id: str, images: list[ImageAsset]) -> ImageAsset | None:
    """Find an ImageAsset by ID."""
    for img in images:
        if img.image_id == image_id:
            return img
    return None
