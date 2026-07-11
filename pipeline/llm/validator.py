"""
JSON extraction + Pydantic validation with retry.

Responsibilities:
1. Extract JSON from raw LLM response (handles markdown fences, reasoning content, etc.)
2. Validate against Pydantic model
3. Retry on failure with configurable attempts
4. Return detailed error information on permanent failure
"""
from __future__ import annotations

import json
import re
import logging
from typing import TypeVar, Type

from pydantic import BaseModel, ValidationError

from pipeline.llm.llm_client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ExtractionError(Exception):
    """Raised when JSON extraction + validation fails after all retries."""

    def __init__(
        self,
        message: str,
        attempts: int,
        last_response: str = "",
        parse_errors: list[str] | None = None,
        validation_errors: list[str] | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_response = last_response
        self.parse_errors = parse_errors or []
        self.validation_errors = validation_errors or []


# ============================================================
# JSON extraction
# ============================================================


def _fix_unescaped_backslashes(text: str) -> str:
    """Fix unescaped backslashes in JSON strings from LLM output.

    LLMs sometimes output \frac inside JSON strings, but JSON requires \\frac.
    """
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            next_char = text[i + 1]
            if next_char in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'):
                # Valid JSON escape, keep as-is
                result.append(text[i:i+2])
                i += 2
            else:
                # Invalid escape, double the backslash
                result.append('\\\\')
                i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)

def extract_json_text(raw: str) -> str | None:
    """Extract a JSON string from raw LLM output.

    Handles:
    - Plain JSON
    - JSON wrapped in markdown code fences (```json ... ```)
    - JSON embedded in reasoning content
    - Leading/trailing whitespace and garbage text

    Returns the JSON string, or None if no JSON found.
    """
    text = raw.strip()
    if not text:
        return None

    # Step 1: Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line (```)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Step 2: Try direct parse
    if _is_valid_json(text):
        return text

    # Step 2.5: Try fixing unescaped backslashes (common LLM issue)
    fixed = _fix_unescaped_backslashes(text)
    if _is_valid_json(fixed):
        return fixed

    # Step 3: Try to find JSON object or array in the text
    # Look for { ... } or [ ... ]
    for pattern in [
        r"\{[\s\S]*\}",  # greedy object
        r"\[[\s\S]*\]",  # greedy array
    ]:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(0)
            if _is_valid_json(candidate):
                return candidate
            candidate_fixed = _fix_unescaped_backslashes(candidate)
            if _is_valid_json(candidate_fixed):
                return candidate_fixed

    # Step 4: Try line-by-line scanning for JSON start
    for i, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            candidate = "\n".join(text.split("\n")[i:])
            if _is_valid_json(candidate):
                return candidate

    return None


def _is_valid_json(text: str) -> bool:
    """Check if text is valid JSON."""
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


# ============================================================
# Validation
# ============================================================

def validate_model(data: dict | list, model_class: Type[T]) -> T:
    """Validate parsed JSON data against a Pydantic model.

    Args:
        data: Parsed JSON data (dict or list).
        model_class: Pydantic model class to validate against.

    Returns:
        Validated model instance.

    Raises:
        ValidationError: If validation fails.
    """
    return model_class.model_validate(data)


# ============================================================
# Extract + Validate (main entry point)
# ============================================================

def extract_and_validate(
    response: LLMResponse,
    model_class: Type[T],
) -> T:
    """Extract JSON from LLM response and validate against Pydantic model.

    Args:
        response: Raw LLM response.
        model_class: Pydantic model to validate against.

    Returns:
        Validated model instance.

    Raises:
        ExtractionError: If extraction or validation fails.
    """
    parse_errors: list[str] = []
    validation_errors: list[str] = []

    # Try content first
    content = response.content.strip()
    if content:
        json_text = extract_json_text(content)
        if json_text:
            try:
                data = json.loads(json_text)
                return validate_model(data, model_class)
            except ValidationError as e:
                validation_errors.append(f"content validation: {_format_validation_error(e)}")
            except json.JSONDecodeError as e:
                parse_errors.append(f"content parse: {e}")
        else:
            parse_errors.append("content: no valid JSON found")
    else:
        parse_errors.append("content: empty")

    # Fallback: try reasoning_content
    rc = response.reasoning_content.strip()
    if rc:
        json_text = extract_json_text(rc)
        if json_text:
            try:
                data = json.loads(json_text)
                return validate_model(data, model_class)
            except ValidationError as e:
                validation_errors.append(f"reasoning validation: {_format_validation_error(e)}")
            except json.JSONDecodeError as e:
                parse_errors.append(f"reasoning parse: {e}")
        else:
            parse_errors.append("reasoning_content: no valid JSON found")

    raise ExtractionError(
        message=f"Failed to extract valid JSON from LLM response",
        attempts=1,
        last_response=content[:500] if content else rc[:500],
        parse_errors=parse_errors,
        validation_errors=validation_errors,
    )


def extract_and_validate_with_retry(
    client: LLMClient,
    system_prompt: str,
    user_prompt: str,
    model_class: Type[T],
    max_retries: int = 2,
    json_schema: dict | None = None,
) -> T:
    """Call LLM, extract JSON, validate, with automatic retry on failure.

    On validation failure, the error message is appended to the user prompt
    for the retry, so the model can correct its output.

    Args:
        client: LLM client instance.
        system_prompt: System message.
        user_prompt: User message.
        model_class: Pydantic model to validate against.
        max_retries: Maximum number of attempts (default 2 = 1 initial + 1 retry).

    Returns:
        Validated model instance.

    Raises:
        ExtractionError: If all attempts fail.
    """
    all_errors: list[str] = []
    last_response = ""

    for attempt in range(max_retries):
        # On retry, append error feedback to prompt
        if attempt == 0:
            current_user_prompt = user_prompt
        else:
            error_summary = "\n".join(all_errors[-3:])  # Last 3 errors
            current_user_prompt = (
                f"{user_prompt}\n\n"
                f"YOUR PREVIOUS RESPONSE WAS INVALID. Error:\n{error_summary}\n\n"
                f"Please return ONLY valid JSON conforming to the schema. No markdown, no explanation."
            )

        try:
            response = client.chat(system=system_prompt, user=current_user_prompt, json_schema=json_schema)
            last_response = response.content or response.reasoning_content

            result = extract_and_validate(response, model_class)

            if attempt > 0:
                logger.info(f"Validation passed on attempt {attempt + 1}")

            return result

        except ExtractionError as e:
            all_errors.append(f"Attempt {attempt + 1}: {e}")
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if e.validation_errors:
                all_errors.extend(e.validation_errors)
            continue

    raise ExtractionError(
        message=f"Failed after {max_retries} attempts",
        attempts=max_retries,
        last_response=last_response[:1000],
        validation_errors=all_errors,
    )


# ============================================================
# Helpers
# ============================================================

def _format_validation_error(e: ValidationError) -> str:
    """Format Pydantic ValidationError into a concise string."""
    errors = []
    for err in e.errors():
        loc = " -> ".join(str(x) for x in err["loc"])
        errors.append(f"{loc}: {err['msg']} (type={err['type']})")
    return "; ".join(errors[:5])  # Limit to 5 errors
