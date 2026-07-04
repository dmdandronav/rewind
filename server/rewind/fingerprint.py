"""Canonical fingerprinting of model requests.

Deterministic replay hinges on one question: *is this agent step asking the model
exactly what it asked last time?* We answer it by hashing a canonical form of the
request — keys sorted, insignificant whitespace removed — so that two logically
identical requests fingerprint the same regardless of dict ordering.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: Request fields that don't affect the model's output and must be excluded from
#: the fingerprint (streaming toggles, client metadata, etc.).
_VOLATILE_KEYS = {"stream", "user", "metadata"}


def fingerprint_request(body: dict[str, Any]) -> str:
    """Return a stable hex digest for a completion request body.

    Volatile fields are stripped so that, e.g., flipping ``stream`` doesn't make
    an otherwise-identical step look different during replay.
    """
    canonical = {k: v for k, v in body.items() if k not in _VOLATILE_KEYS}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
