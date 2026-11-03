"""Fail-closed release gate adapted from kenya-afya-bot's pilot readiness check."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from apps.api.afya import core
from evals.fingerprint import code_fingerprint


def check() -> dict:
    failures = []
    sources = core.sources()
    if len(sources) < 9 or any(source["status"] != "approved" for source in sources):
        failures.append("All nine current source versions must be approved")
    for source in sources:
        path = core.PDF_DIR / source["filename"]
        if not path.is_file() or core.digest(path) != source["sha256"]:
            failures.append(f"Source hash mismatch: {source['filename']}")
    index = core.index_status()
    passages, embeddings = index["passages"], index["embeddings"]
    if index["status"] != "ready":
        failures.append("Semantic index is missing or stale")

    report_path = core.ROOT / "evals/runs/review-seed-44-latest.json"
    if not report_path.is_file():
        failures.append("The 44-case review run is missing")
        report = None
    else:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        case_path = core.ROOT / "evals/cases/review-seed-44.json"
        expected_ids = {case["id"] for case in json.loads(case_path.read_text(encoding="utf-8"))}
        results = report.get("results", [])
        result_ids = [row.get("id") for row in results]
        if (report.get("case_set") != "review-seed-44" or report.get("cases") != 44
                or len(results) != 44 or set(result_ids) != expected_ids or len(set(result_ids)) != 44):
            failures.append("The review run does not contain all 44 cases")
        if report.get("case_set_fingerprint") != hashlib.sha256(case_path.read_bytes()).hexdigest():
            failures.append("Case set changed after the review run")
        stored_fingerprint = report.get("run_fingerprint")
        unsigned_report = {key: value for key, value in report.items() if key != "run_fingerprint"}
        actual_fingerprint = hashlib.sha256(json.dumps(unsigned_report, sort_keys=True).encode("utf-8")).hexdigest()
        if stored_fingerprint != actual_fingerprint:
            failures.append("Review run contents changed after generation")
        active_hashes = {row["filename"]: row["sha256"] for row in sources if row["status"] == "approved"}
        for result in results:
            citations = result.get("citations") or []
            if result.get("status") == "answered" and not citations:
                failures.append(f"Answered case has no citations: {result.get('id')}")
            if any(active_hashes.get(citation.get("filename")) != citation.get("sha256") for citation in citations):
                failures.append(f"Case cites a changed or unapproved source: {result.get('id')}")
        if report.get("source_fingerprint") != core.source_fingerprint():
            failures.append("Approved sources changed after the review run")
        if report.get("code_fingerprint") != code_fingerprint():
            failures.append("Answer code changed after the review run")
        if report.get("model") != os.getenv("AFYA_CHAT_MODEL", "llama3.1:8b"):
            failures.append("Answer model changed after the review run")
        if report.get("model_provider") != os.getenv("AFYA_LLM_PROVIDER", "ollama"):
            failures.append("Answer provider changed after the review run")
        if report.get("embedding_model") != os.getenv("AFYA_EMBED_MODEL", "nomic-embed-text:latest"):
            failures.append("Embedding model changed after the review run")

    review_path = core.ROOT / "evals/reviews/clinical-adjudication.json"
    if not review_path.is_file():
        failures.append("Named clinical adjudications are missing")
        reviews = []
    else:
        reviews = json.loads(review_path.read_text(encoding="utf-8"))
    by_case = {}
    for review in reviews:
        ratings = review.get("ratings") or {}
        if (review.get("decision") != "pass" or any(ratings.get(key) != "pass" for key in
                ("medical_accuracy", "source_support", "public_clarity", "safety"))
                or not review.get("reviewer") or not review.get("role")
                or not review.get("reviewed_at") or report is None
                or review.get("run_fingerprint") != report.get("run_fingerprint")):
            continue
        by_case.setdefault(review.get("case_id"), set()).add(review["reviewer"].strip().casefold())
    if report is not None:
        missing = [row["id"] for row in report.get("results", []) if len(by_case.get(row["id"], set())) < 2]
        if missing:
            failures.append(f"Two independent passing reviews are missing for {len(missing)} cases")
    signoff = core.ROOT / "evals/reviews/authority-signoff.json"
    if not signoff.is_file():
        failures.append("Accountable health authority signoff is missing")
    else:
        authority = json.loads(signoff.read_text(encoding="utf-8"))
        if (report is None or authority.get("run_fingerprint") != report.get("run_fingerprint")
                or not authority.get("approver") or not authority.get("role") or not authority.get("approved_at")):
            failures.append("Authority signoff does not match the current reviewed run")
    return {"ready": not failures, "failures": failures, "source_count": len(sources),
            "passages": passages, "embeddings": embeddings}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = check()
    print(json.dumps(result, indent=2))
    if args.strict and not result["ready"]:
        raise SystemExit(1)
