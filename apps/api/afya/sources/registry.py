"""Register new PDF metadata before import and human approval."""
from __future__ import annotations

import json
from pathlib import Path

from .. import core


def register(filename: str, tier: str, diseases: list[str], source_url: str | None = None) -> dict:
    if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        raise ValueError("filename must be a PDF basename")
    if tier not in {"public", "clinical", "restricted"}:
        raise ValueError("tier must be public, clinical, or restricted")
    normalized = list(dict.fromkeys(name.strip() for name in diseases if name.strip()))
    if not normalized:
        raise ValueError("At least one disease tag is required")
    if source_url and not source_url.startswith("https://"):
        raise ValueError("source_url must be HTTPS")
    records = json.loads(core.MANIFEST.read_text(encoding="utf-8"))
    if any(row["filename"].casefold() == filename.casefold() for row in records):
        raise ValueError("Source already registered")
    record = {"filename": filename, "tier": tier, "diseases": normalized,
              "source_url": source_url, "legacy_sha256": None, "legacy_approval": None}
    records.append(record)
    core.MANIFEST.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return record
