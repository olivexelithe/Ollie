from __future__ import annotations

import hashlib
import re
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
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8]
    return f"OLL-{digest.upper()}"


def first_non_empty(values: Iterable[str | None]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""

