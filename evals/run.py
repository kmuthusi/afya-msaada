"""Unreviewed smoke screen; never interprets lexical overlap as clinical correctness."""
import json
from datetime import datetime, timezone
from pathlib import Path

from apps.api.afya import core


def run():
    cases = json.loads((core.ROOT / "evals/cases/filovirus-seed.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        result = core.answer(case["question"])
        concept_hits = [any(term.lower() in result["answer"].lower() for term in group)
                        for group in case.get("expected_concepts", [])]
        prohibited = [term for term in case.get("prohibited_phrases", []) if term.lower() in result["answer"].lower()]
        anchor = case.get("anchor") or {}
        citation_anchor_match = any(c["filename"] == anchor.get("source") and c["page"] == anchor.get("page")
                                    for c in result["citations"])
        rows.append({"id": case["id"], "question": case["question"], "expected_behavior": case["expected_behavior"],
                     "status": result["status"], "reason": result["reason"], "answer": result["answer"],
                     "citations": result["citations"], "concept_hits": concept_hits,
                     "prohibited_found": prohibited, "anchor_page_cited": citation_anchor_match,
                     "needs_clinical_review": True})
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "cases": len(rows),
              "answered": sum(r["status"] == "answered" for r in rows),
              "declined": sum(r["status"] == "declined" for r in rows),
              "concept_complete": sum(bool(r["concept_hits"]) and all(r["concept_hits"]) for r in rows),
              "anchor_page_cited": sum(r["anchor_page_cited"] for r in rows),
              "clinical_approval": False, "results": rows}
    target = core.ROOT / "evals/runs/latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    run()
