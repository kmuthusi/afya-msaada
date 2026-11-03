"""Stable fingerprints for answer behavior and case definitions."""
import hashlib

from apps.api.afya import core


ANSWER_FILES = (
    "apps/api/afya/core.py",
    "apps/api/afya/main.py",
    "apps/api/afya/answering/pipeline.py",
    "apps/api/afya/conversation/context.py",
    "apps/api/afya/policy/guard.py",
    "apps/api/afya/retrieval/planner.py",
    "apps/api/afya/sources/processor.py",
    "apps/api/afya/models/ollama.py",
    "apps/api/afya/models/provider.py",
    "evals/run.py",
)


def code_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative in ANSWER_FILES:
        digest.update(relative.encode("utf-8"))
        digest.update((core.ROOT / relative).read_bytes())
    return digest.hexdigest()
