from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Iterable


NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.casefold().strip()
    return NON_ALNUM_RE.sub("", lowered)


def compact_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def stable_issue_id(*parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:6]
    return f"OL-{digest.upper()}"


def first_non_empty(values: Iterable[str | None]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def names_loosely_match(left: str | None, right: str | None, threshold: float = 0.72) -> bool:
    left_norm = normalize_name(left)
    right_norm = normalize_name(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if left_norm in right_norm or right_norm in left_norm:
        return True
    return SequenceMatcher(None, left_norm, right_norm).ratio() >= threshold
