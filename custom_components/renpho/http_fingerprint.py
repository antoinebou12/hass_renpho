"""HTTP client fingerprints (headers) for Renpho API requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional


@dataclass(frozen=True)
class ClientFingerprint:
    """Optional headers that mimic a mobile Renpho client."""

    user_agent: str
    accept_language: Optional[str] = None
    extra_headers: Mapping[str, str] = field(default_factory=dict)


def renpho_ios_default() -> ClientFingerprint:
    return ClientFingerprint(
        user_agent="Renpho/2.1.0 (iPhone; iOS 14.4; Scale/2.1.0; en-US)",
        accept_language="en-US",
    )


def renpho_android_default() -> ClientFingerprint:
    return ClientFingerprint(
        user_agent="Renpho/2.1.0 (Linux; Android 13; Scale/2.1.0; en-US)",
        accept_language="en-US",
    )


def merge_headers(
    base: Dict[str, str],
    fingerprint: ClientFingerprint,
) -> Dict[str, str]:
    """Merge JSON API defaults with fingerprint headers (fingerprint wins on conflict)."""
    out = dict(base)
    out["User-Agent"] = fingerprint.user_agent
    if fingerprint.accept_language:
        out["Accept-Language"] = fingerprint.accept_language
    out.update(dict(fingerprint.extra_headers))
    return out
