"""
Convert MinerU content_list_v2 (and model.json) into a NormalizedDocument.

This is one of potentially many converters. The rest of the pipeline
only works with NormalizedDocument, never with MinerU-specific formats.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from pipeline.schema import (
    SCHEMA_VERSION, PIPELINE_VERSION,
    Block, BlockType, BBox, Inline, InlineType, ImageAsset, Page,
    NormalizedDocument, Provenance,
    make_document_id, make_block_id, make_image_id,
)

TOOL_NAME = "mineru"
TOOL_VERSION = "3.4.2"  # Will be overridden if metadata available
COMPONENT = "normalizer"


def convert(
    content_list_v2_path: Path,
    model_json_path: Path | None = None,
    output_dir: Path | None = None,
    source_pdf_path: str = "",
) -> NormalizedDocument:
    """
    Convert MinerU content_list_v2 to NormalizedDocument.

    Args:
        content_list_v2_path: Path to the content_list_v2.json file.
        model_json_path: Optional path to the model.json file (for image refs).
        output_dir: Where to save the NormalizedDocument JSON.
        source_pdf_path: Original PDF path (for metadata).

    Returns:
        NormalizedDocument instance.
    """
    # Load MinerU outputs
    raw_pages = json.loads(content_list_v2_path.read_text(encoding="utf-8"))
    raw_images = _load_model_images(model_json_path) if model_json_path else []

    # Generate document ID
    source_dir = content_list_v2_path.parent
    pdf_name = source_pdf_path or str(source_dir)
    document_id = make_document_id(pdf_name)

    # Build provenance factory
    now = datetime.now(timezone.utc).isoformat()
    def make_source(raw_id: str | None, page: int) -> Provenance:
        return Provenance(
            source_tool=TOOL_NAME,
            source_version=TOOL_VERSION,
            source_raw_id=raw_id,
            source_page=page,
            component=COMPONENT,
            component_version=PIPELINE_VERSION,
            created_at=now,
        )

    # Convert each page
    block_seq = 0
    img_seq = 0
    pages: list[Page] = []
    images: list[ImageAsset] = []

    for page_idx, raw_page_items in enumerate(raw_pages):
        page_number = page_idx + 1

        # Determine page dimensions from first item's bbox if available
        page_width = 595.0  # A4 default
        page_height = 841.0

        blocks: list[Block] = []

        for item_idx, raw_item in enumerate(raw_page_items):
            raw_type = raw_item.get("type", "unknown")
            raw_bbox = raw_item.get("bbox", [0, 0, 0, 0])
            raw_content = raw_item.get("content", {})

            # Map MinerU type to our BlockType
            block_type = _map_block_type(raw_type)

            # Build the block
            block_seq += 1
            block_id = make_block_id(document_id, block_seq)
            source = make_source(str(item_idx), page_number)

            bbox = BBox.from_list(raw_bbox) if len(raw_bbox) >= 4 else BBox(0, 0, 0, 0)

            block = Block(
                id=block_id,
                page=page_number,
                type=block_type,
                bbox=bbox,
                reading_order=item_idx,
                source=source,
            )

            # Fill type-specific fields
            if block_type == BlockType.title:
                title_items = raw_content.get("title_content", [])
                block.title_content = _convert_inline_list(title_items)
                block.level = raw_content.get("level", 1)

            elif block_type in (BlockType.paragraph, BlockType.list_item):
                para_items = raw_content.get("paragraph_content", [])
                block.inline_content = _convert_inline_list(para_items)

            elif block_type == BlockType.formula_block:
                math_content = raw_content.get("math_content", "")
                block.latex = math_content
                block.math_type = raw_content.get("math_type", "latex")
                # Check for image source
                img_src = raw_content.get("image_source")
                if img_src and "path" in img_src:
                    img_seq += 1
                    img_id = make_image_id(document_id, img_seq)
                    img_path = img_src.get("path", "")
                    images.append(ImageAsset(
                        image_id=img_id,
                        path=img_path,
                        mime_type=_guess_mime(img_path),
                        source=source,
                    ))
                    block.image_ref = img_id

            elif block_type == BlockType.equation_interline:
                math_content = raw_content.get("math_content", "")
                block.latex = math_content
                block.math_type = raw_content.get("math_type", "latex")
                img_src = raw_content.get("image_source")
                if img_src and "path" in img_src:
                    img_seq += 1
                    img_id = make_image_id(document_id, img_seq)
                    img_path = img_src.get("path", "")
                    images.append(ImageAsset(
                        image_id=img_id,
                        path=img_path,
                        mime_type=_guess_mime(img_path),
                        source=source,
                    ))
                    block.image_ref = img_id

            elif block_type == BlockType.table:
                # Extract text from table HTML (tables with formulas/questions)
                table_html = raw_content.get("html", "")
                if table_html:
                    extracted = _extract_from_table_html(table_html)
                    if extracted:
                        block.inline_content = extracted
                        # Promote to paragraph for downstream processing
                        block.type = BlockType.paragraph

            elif block_type in (BlockType.page_header, BlockType.page_footer, BlockType.aside):
                block.text = _extract_text_from_content(raw_content)

            elif block_type == BlockType.page_number:
                block.text = _extract_text_from_content(raw_content)

            blocks.append(block)

        pages.append(Page(
            page_number=page_number,
            width=page_width,
            height=page_height,
            blocks=blocks,
        ))

    # Build document
    doc = NormalizedDocument(
        document_id=document_id,
        source_path=source_pdf_path,
        tool=TOOL_NAME,
        tool_version=TOOL_VERSION,
        tool_raw_dir=str(source_dir),
        pages=pages,
        images=images,
        metadata={
            "source_file": str(content_list_v2_path),
            "total_blocks": block_seq,
            "total_images": img_seq,
        },
    )

    # Save if output_dir specified
    if output_dir:
        out_path = output_dir / "normalized.json"
        doc.save(out_path)

    return doc


# ============================================================
# Internal helpers
# ============================================================

def _map_block_type(mineru_type: str) -> BlockType:
    """Map MinerU content_list_v2 type to our BlockType."""
    mapping = {
        "title": BlockType.title,
        "paragraph": BlockType.paragraph,
        "list_item": BlockType.list_item,
        "table": BlockType.table,
        "figure": BlockType.figure,
        "equation_interline": BlockType.equation_interline,
        "equation_block": BlockType.formula_block,
        "page_header": BlockType.page_header,
        "page_footer": BlockType.page_footer,
        "page_number": BlockType.page_number,
        "page_aside_text": BlockType.aside,
        "aside_text": BlockType.aside,
        "caption": BlockType.caption,
    }
    return mapping.get(mineru_type, BlockType.unknown)


def _map_inline_type(mineru_type: str) -> InlineType:
    """Map MinerU inline content type to our InlineType."""
    mapping = {
        "text": InlineType.text,
        "equation_inline": InlineType.formula,
        "equation_interline": InlineType.formula,
        "equation_display": InlineType.formula,
        "image": InlineType.image,
    }
    return mapping.get(mineru_type, InlineType.unknown)


def _convert_inline_list(raw_items: list[dict]) -> list[Inline]:
    """Convert a list of MinerU inline content items to our Inline list."""
    result = []
    for item in raw_items:
        raw_type = item.get("type", "text")
        content = item.get("content", "")
        result.append(Inline(
            type=_map_inline_type(raw_type),
            content=content if isinstance(content, str) else str(content),
        ))
    return result



def _extract_from_table_html(html: str) -> list[Inline] | None:
    """Extract text and formulas from a MinerU table HTML block.

    The HTML is a <table> with <td> cells that may contain
    text and inline LaTeX ($...$). We flatten all cells into
    a list of Inline items suitable for a paragraph block.
    """
    import re
    import html as html_mod

    # Strip <table>, </table>, <tr>, </tr> tags, keep <td> content
    text = re.sub(r'<table>|</table>|<tr>|</tr>', '', html, flags=re.IGNORECASE)
    # Replace </td><td> with newline separator
    text = re.sub(r'</td>\s*<td[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = html_mod.unescape(text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    if not text or len(text) < 5:
        return None

    # Split on $...$ to extract inline math
    inlines: list[Inline] = []
    parts = re.split(r"(\$[^$]+\$)", text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("$") and part.endswith("$"):
            latex = part[1:-1]
            inlines.append(Inline(
                type=InlineType.formula,
                content=latex,
            ))
        else:
            inlines.append(Inline(
                type=InlineType.text,
                content=part,
            ))

    return inlines if inlines else None


def _extract_text_from_content(raw_content: dict) -> str:
    """Extract plain text from MinerU content dict (for headers, page numbers, etc.)."""
    if isinstance(raw_content, str):
        return raw_content
    # page_header / page_number often have text_content or direct text
    for key in ("text_content", "content", "text"):
        val = raw_content.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, list):
            parts = []
            for sub in val:
                if isinstance(sub, dict):
                    parts.append(sub.get("content", ""))
                elif isinstance(sub, str):
                    parts.append(sub)
            return "".join(parts)
    return ""


def _load_model_images(model_path: Path) -> list[dict]:
    """Load image detections from model.json (used for additional image refs)."""
    try:
        data = json.loads(model_path.read_text(encoding="utf-8"))
        images = []
        for page in data:
            for det in page.get("layout_dets", []):
                if det.get("label") in ("figure", "image"):
                    images.append(det)
        return images
    except Exception:
        return []


def _guess_mime(path: str) -> str:
    """Guess MIME type from file extension."""
    ext = Path(path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(ext, "image/png")


def main():
    """CLI entry point for testing."""
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.converters.mineru_v2 <content_list_v2.json> [model.json] [output_dir]")
        sys.exit(1)

    v2_path = Path(sys.argv[1])
    model_path = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    out_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else v2_path.parent / "normalized"
    source_pdf = sys.argv[4] if len(sys.argv) > 4 else ""

    doc = convert(v2_path, model_path, out_dir, source_pdf_path=source_pdf)
    print(f"Document ID: {doc.document_id}")
    print(f"Pages: {len(doc.pages)}")
    print(f"Total blocks: {sum(len(p.blocks) for p in doc.pages)}")
    print(f"Total images: {len(doc.images)}")
    print(f"Saved to: {out_dir / 'normalized.json'}")


if __name__ == "__main__":
    main()
