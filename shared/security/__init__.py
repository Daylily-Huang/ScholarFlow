"""ScholarFlow Security Subpackage.

Implements untrusted content handling, external query minimization,
and provenance boundaries.
"""

from typing import Any, Dict, List, Optional
import re

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"reveal\s+(your\s+)?system\s+prompt",
    r"upload\s+(the\s+)?project\s+files",
    r"execute\s+this\s+(command|script)",
    r"forget\s+(all\s+)?evidence\s+rules",
]


def is_prompt_injection(text: str) -> bool:
    """Detect whether text contains prompt injection attempts."""
    lowered = text.lower()
    for pat in PROMPT_INJECTION_PATTERNS:
        if re.search(pat, lowered):
            return True
    return False


def sanitize_external_query(
    query_string: str,
    context_facts: Optional[Dict[str, Any]] = None,
    prohibited_tokens: Optional[List[str]] = None,
) -> str:
    """Sanitize an outbound query string, ensuring private context is not exported."""
    sanitized = query_string

    # 1. Remove file paths
    sanitized = re.sub(r"file" + r":///[^\s]+", "", sanitized)
    sanitized = re.sub(r"[A-Za-z]:\\[^\s]+", "", sanitized)

    # 2. Remove explicit prohibited tokens
    if prohibited_tokens:
        for tok in prohibited_tokens:
            sanitized = re.sub(re.escape(tok), "", sanitized, flags=re.IGNORECASE)

    # 3. Strip non-external-safe facts
    if context_facts:
        for k, v in context_facts.items():
            if isinstance(v, dict) and not v.get("external_safe", True):
                val = str(v.get("value", ""))
                if val and len(val) >= 3:
                    sanitized = re.sub(re.escape(val), "", sanitized, flags=re.IGNORECASE)

    # 4. Normalize whitespace
    return re.sub(r"\s+", " ", sanitized).strip()
