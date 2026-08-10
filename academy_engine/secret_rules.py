"""Canonical byte-oriented secret rules shared by Academy verification surfaces."""

from __future__ import annotations

import re
from collections.abc import Iterator


FIXED_SECRET_RULES = (
    (
        "PEM_PRIVATE_KEY",
        re.compile(
            rb"(?<![A-Za-z0-9_])-----BEGIN[ \t]+"
            rb"(?:RSA[ \t]+|EC[ \t]+|OPENSSH[ \t]+|DSA[ \t]+|ENCRYPTED[ \t]+)?"
            rb"PRIVATE[ \t]+KEY-----(?![A-Za-z0-9_])"
        ),
    ),
    (
        "GITHUB_TOKEN",
        re.compile(
            rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,255}(?![A-Za-z0-9_])"
        ),
    ),
    (
        "GITHUB_TOKEN",
        re.compile(
            rb"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,255}"
            rb"(?![A-Za-z0-9_])"
        ),
    ),
    (
        "AWS_ACCESS_KEY_ID",
        re.compile(
            rb"(?<![A-Za-z0-9_])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9_])"
        ),
    ),
    (
        "OPENAI_API_KEY",
        re.compile(
            rb"(?<![A-Za-z0-9_-])sk-(?!proj-)[A-Za-z0-9_-]{20,255}"
            rb"(?![A-Za-z0-9_-])"
        ),
    ),
    (
        "OPENAI_API_KEY",
        re.compile(
            rb"(?<![A-Za-z0-9_-])sk-proj-[A-Za-z0-9_-]{20,255}"
            rb"(?![A-Za-z0-9_-])"
        ),
    ),
    (
        "SLACK_TOKEN",
        re.compile(
            rb"(?<![A-Za-z0-9_-])xox[A-Za-z]-[A-Za-z0-9-]{20,255}"
            rb"(?![A-Za-z0-9_-])"
        ),
    ),
    (
        "CREDENTIAL_URL",
        re.compile(
            rb"(?<![A-Za-z0-9_])https?://[A-Za-z0-9._~-]+:"
            rb"[A-Za-z0-9._~+/-]{12,255}@[A-Za-z0-9.-]+"
            rb"(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~!$&'()*+,;=:@%/?#-]*)?"
            rb"(?![A-Za-z0-9._~+/-])",
            re.IGNORECASE,
        ),
    ),
    (
        "BEARER_AUTHORIZATION",
        re.compile(
            rb"(?<![A-Za-z0-9_-])Authorization[ \t]*:[ \t]*Bearer[ \t]+"
            rb"[A-Za-z0-9._~+/-]{20,255}={0,2}(?![A-Za-z0-9._~+/-=])",
            re.IGNORECASE,
        ),
    ),
)
ASSIGNMENT = re.compile(
    rb"^[ \t]*(?:api_key|access_token|secret|password|passwd)[ \t]*[:=][ \t]*"
    rb"(?:\"(?P<double>[^\"\r\n]{16,255})\"|'(?P<single>[^'\r\n]{16,255})'|"
    rb"(?P<bare>[^\s#;,\"']{16,255}))"
    rb"[ \t]*(?:[#;][^\r\n]*)?\r?$",
    re.IGNORECASE | re.MULTILINE,
)
MALFORMED_ASSIGNMENT = re.compile(
    rb"^[ \t]*(?:api_key|access_token|secret|password|passwd)[ \t]*[:=][ \t]*"
    rb"(?:\"(?P<double_malformed>[^\"'\r\n]{16,255}?)(?:')?|"
    rb"'(?P<single_malformed>[^\"'\r\n]{16,255}?)(?:\")?)"
    rb"[ \t]*(?:[#;][^\r\n]*)?\r?$",
    re.IGNORECASE | re.MULTILINE,
)
PLACEHOLDER_VALUES = frozenset(
    (b"placeholder-value", b"example-credential", b"not-a-real-secret")
)
ENVIRONMENT_REFERENCE = re.compile(rb"\$\{[A-Z][A-Z0-9_]{0,63}\}")


def _is_placeholder(value: bytes) -> bool:
    return value in PLACEHOLDER_VALUES or ENVIRONMENT_REFERENCE.fullmatch(value) is not None


def iter_secret_matches(data: bytes) -> Iterator[tuple[str, int]]:
    """Yield each distinct canonical secret rule and byte offset in one byte view."""
    seen: set[tuple[str, int]] = set()
    for rule, pattern in FIXED_SECRET_RULES:
        for match in pattern.finditer(data):
            item = (rule, match.start())
            if item not in seen:
                seen.add(item)
                yield item
    for match in ASSIGNMENT.finditer(data):
        group = next(
            name for name in ("double", "single", "bare") if match.group(name) is not None
        )
        value = match.group(group)
        if not _is_placeholder(value):
            item = ("CREDENTIAL_ASSIGNMENT", match.start(group))
            if item not in seen:
                seen.add(item)
                yield item
    for match in MALFORMED_ASSIGNMENT.finditer(data):
        group = next(
            name
            for name in ("double_malformed", "single_malformed")
            if match.group(name) is not None
        )
        value = match.group(group)
        if not _is_placeholder(value):
            item = ("CREDENTIAL_ASSIGNMENT", match.start(group))
            if item not in seen:
                seen.add(item)
                yield item


def iter_secret_content_views(content: bytes) -> Iterator[bytes]:
    """Yield raw bytes and a strict UTF-8 view for BOM-declared UTF-16 content."""
    yield content
    if content.startswith(b"\xff\xfe"):
        encoding = "utf-16-le"
    elif content.startswith(b"\xfe\xff"):
        encoding = "utf-16-be"
    else:
        return
    decoded = content[2:].decode(encoding, errors="strict")
    yield decoded.encode("utf-8")


def blob_is_secret_free(content: bytes) -> bool:
    """Fail closed on canonical findings or malformed BOM-declared UTF-16."""
    try:
        return all(
            next(iter_secret_matches(view), None) is None
            for view in iter_secret_content_views(content)
        )
    except UnicodeDecodeError:
        return False
