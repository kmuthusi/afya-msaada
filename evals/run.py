"""Unreviewed smoke screen; never interprets lexical overlap as clinical correctness."""
import json
import argparse
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from apps.api.afya import core
from evals.fingerprint import code_fingerprint


def run(case_set: str = "filovirus-seed"):
    if case_set not in {"filovirus-seed", "review-seed-44"}:
        raise ValueError("Unknown case set")
    case_path = core.ROOT / f"evals/cases/{case_set}.json"
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        result = core.answer(case["question"], case.get("history", []))
        concept_hits = [any(term.lower() in result["answer"].lower() for term in group)
                        for group in case.get("expected_concepts", [])]
        prohibited = [term for term in case.get("prohibited_phrases", []) if term.lower() in result["answer"].lower()]
        anchor = case.get("anchor") or {}
        citation_anchor_match = any(c["filename"] == anchor.get("source") and c["page"] == anchor.get("page")
                                    for c in result["citations"])
        rows.append({"id": case["id"], "question": case["question"], "expected_behavior": case.get("expected_behavior"),
                     "category": case.get("category") or case.get("domain"), "disease": case.get("disease"),
                     "language": case.get("language", "en"), "history": case.get("history", []),
                     "review_focus": case.get("focus"),
                     "status": result["status"], "reason": result["reason"], "answer": result["answer"],
                     "citations": result["citations"], "concept_hits": concept_hits,
                     "prohibited_found": prohibited, "anchor_page_cited": citation_anchor_match,
                     "needs_clinical_review": True})
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "case_set": case_set, "cases": len(rows),
              "source_fingerprint": core.source_fingerprint(), "code_fingerprint": code_fingerprint(),
              "case_set_fingerprint": hashlib.sha256(case_path.read_bytes()).hexdigest(),
              "model_provider": os.getenv("AFYA_LLM_PROVIDER", "ollama"),
              "model": os.getenv("AFYA_CHAT_MODEL", "llama3.1:8b"),
              "embedding_model": os.getenv("AFYA_EMBED_MODEL", "nomic-embed-text:latest"),
              "answered": sum(r["status"] == "answered" for r in rows),
              "declined": sum(r["status"] == "declined" for r in rows),
              "concept_evaluable": sum(bool(r["concept_hits"]) for r in rows),
              "concept_complete": sum(bool(r["concept_hits"]) and all(r["concept_hits"]) for r in rows),
              "anchor_page_cited": sum(r["anchor_page_cited"] for r in rows),
              "clinical_approval": False, "results": rows}
    report["run_fingerprint"] = hashlib.sha256(json.dumps(report, sort_keys=True).encode("utf-8")).hexdigest()
    target = core.ROOT / f"evals/runs/{case_set}-latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-set", choices=("filovirus-seed", "review-seed-44"), default="filovirus-seed")
    run(parser.parse_args().case_set)
