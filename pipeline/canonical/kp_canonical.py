"""
Knowledge Point Canonicalizer.

Loads alias mappings from kp_aliases.json and normalizes LLM-generated
knowledge point names to canonical forms.

Design:
- Alias file is a flat JSON dict: {"别名": "标准名", ...}
- normalize("某个变体") -> "标准名称" (or original if no mapping)
- Thread-safe: alias dict is rebuilt atomically on reload
- Supports runtime additions via add_alias()
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ALIASES_PATH = Path(__file__).parent / "kp_aliases.json"

# Internal alias map — loaded once, reloaded on demand
_alias_map: dict[str, str] = {}
_loaded = False


def _ensure_loaded() -> None:
    """Lazy-load the alias map on first use."""
    global _alias_map, _loaded
    if _loaded:
        return
    reload_aliases()


def reload_aliases() -> None:
    """(Re)load alias mappings from the JSON file."""
    global _alias_map, _loaded
    if not ALIASES_PATH.exists():
        logger.warning(f"Alias file not found: {ALIASES_PATH}")
        _alias_map = {}
        _loaded = True
        return

    raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    # Strip internal comment keys
    _alias_map = {k: v for k, v in raw.items() if not k.startswith("_")}
    _loaded = True
    logger.info(f"Loaded {len(_alias_map)} KP aliases from {ALIASES_PATH.name}")


def normalize_kp_name(name: str) -> str:
    """Normalize a single knowledge point name.

    Returns the canonical name if an alias mapping exists,
    otherwise returns the original name unchanged.
    """
    _ensure_loaded()
    name = name.strip()
    return _alias_map.get(name, name)


def normalize_kp_list(kps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize knowledge point names in a list of KP dicts.

    Each dict must have a 'name' key. The 'name' field is replaced
    with the canonical form. Other fields are untouched.

    Returns a new list (does not mutate the input).
    """
    result = []
    for kp in kps:
        kp = dict(kp)  # shallow copy
        original = kp.get("name", "")
        canonical = normalize_kp_name(original)
        if canonical != original:
            logger.debug(f"KP normalized: '{original}' -> '{canonical}'")
        kp["name"] = canonical
        result.append(kp)
    return result


def normalize_enrichment_kps(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Normalize KP names inside an enrichment dict.

    Expects the structure produced by enricher.py:
        {"knowledge_points": [{"name": ..., "chapter": ..., ...}, ...], ...}

    Returns a new dict (does not mutate the input).
    """
    enrichment = dict(enrichment)
    kps = enrichment.get("knowledge_points", [])
    enrichment["knowledge_points"] = normalize_kp_list(kps)
    return enrichment


def add_alias(alias: str, canonical: str) -> None:
    """Add a new alias mapping at runtime.

    Also persists to the JSON file so it survives restarts.
    """
    _ensure_loaded()
    alias = alias.strip()
    canonical = canonical.strip()
    if not alias or not canonical:
        return

    old = _alias_map.get(alias)
    _alias_map[alias] = canonical

    # Persist to file
    try:
        raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
        raw[alias] = canonical
        ALIASES_PATH.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(f"Added KP alias: '{alias}' -> '{canonical}'")
    except Exception as e:
        logger.error(f"Failed to persist alias '{alias}': {e}")


def get_all_canonical_names() -> set[str]:
    """Return all known canonical (standard) names."""
    _ensure_loaded()
    return set(_alias_map.values())
