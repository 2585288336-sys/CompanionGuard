from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class NumericToken:
    raw: str
    normalized: str
    type: str
    start: int
    end: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_IDENTIFIER_RE = re.compile(
    r"(?:[A-Za-z_][A-Za-z0-9_]*(?:[-_][A-Za-z0-9_]+)+|[A-Za-z_][A-Za-z0-9_]*|\d+(?:[-_][A-Za-z0-9_]+)+)"
)
_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pp", re.compile(r"[+-]?\d+(?:\.\d+)?\s*pp\b")),
    ("percentage", re.compile(r"[+-]?\d+(?:\.\d+)?\s*%")),
    ("decimal", re.compile(r"[+-]?\d+\.\d+")),
    ("integer", re.compile(r"[+-]?\d+")),
)


def _normalized(raw: str, token_type: str) -> str:
    if token_type == "percentage":
        return re.sub(r"\s+", "", raw)
    if token_type == "pp":
        return re.sub(r"\s+", " ", raw.strip())
    return raw.strip()


def _numeric_match_is_bounded(text: str, start: int, end: int) -> bool:
    previous = text[start - 1] if start else ""
    following = text[end] if end < len(text) else ""
    if start and ((previous.isascii() and previous.isalnum()) or previous in "_-"):
        return False
    if end < len(text) and ((following.isascii() and following.isalnum()) or following == "_"):
        return False
    return True


def scan_numeric_tokens(text: str) -> list[NumericToken]:
    """Scan atomic numeric literals once, preserving source spans and identifiers."""
    tokens: list[NumericToken] = []
    index = 0
    while index < len(text):
        identifier = _IDENTIFIER_RE.match(text, index)
        if identifier:
            index = identifier.end()
            continue
        matched = False
        for token_type, pattern in _TOKEN_PATTERNS:
            match = pattern.match(text, index)
            if not match or not _numeric_match_is_bounded(text, match.start(), match.end()):
                continue
            raw = match.group(0)
            tokens.append(NumericToken(
                raw=raw,
                normalized=_normalized(raw, token_type),
                type=token_type,
                start=match.start(),
                end=match.end(),
            ))
            index = match.end()
            matched = True
            break
        if not matched:
            index += 1
    return tokens


def allowed_numeric_token_inventory(value: Any) -> set[str]:
    """Build provenance inventory with the same lexer used for report text."""
    inventory: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            inventory.update(allowed_numeric_token_inventory(item))
    elif isinstance(value, list):
        for item in value:
            inventory.update(allowed_numeric_token_inventory(item))
    elif value is not None:
        inventory.update(token.normalized for token in scan_numeric_tokens(str(value)))
    return inventory
