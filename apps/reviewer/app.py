"""Local answer-review workbench. Run with Streamlit on loopback only."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from apps.api.afya import core


REPORT = core.ROOT / "evals/runs/review-seed-44-latest.json"
REVIEWS = core.ROOT / "evals/reviews/clinical-adjudication.json"
CRITERIA = ("medical_accuracy", "source_support", "public_clarity", "safety")


def record(review: dict) -> None:
    REVIEWS.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.is_file() else []
    history.append(review)
    REVIEWS.write_text(json.dumps(history, indent=2), encoding="utf-8")


def main() -> None:
    st.set_page_config(page_title="Afya Msaada review", layout="wide")
    st.title("Afya Msaada answer review")
    st.caption("Local review aid. Reviewer names and roles are self-reported; institutional verification is still required.")
    secret = os.getenv("AFYA_REVIEWER_PASSWORD", "")
    if len(secret) < 16:
        st.error("Set AFYA_REVIEWER_PASSWORD to a strong local password before opening this workbench.")
        st.stop()
    entered = st.text_input("Local reviewer password", type="password")
    if entered != secret:
        st.stop()
    if not REPORT.is_file():
        st.warning("Generate the 44-case packet: python -m evals.run --case-set review-seed-44")
        st.stop()
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    rows = report.get("results", [])
    if len(rows) != 44:
        st.error("The packet does not contain all 44 cases.")
        st.stop()
    selected = st.selectbox("Case", rows, format_func=lambda r: f"{r['id']}: {r['question']}")
    st.subheader(selected["question"])
    if selected.get("review_focus"):
        st.info(f"Review focus: {selected['review_focus']}")
    if selected.get("history"):
        st.write("**Prior user questions:**", selected["history"])
    st.write("**Answer status:**", selected["status"])
    st.write("**Answer:**", selected["answer"])
    st.write("**Decline reason:**", selected["reason"])
    for citation in selected.get("citations", []):
        filename = citation["filename"]
        page = citation["page"]
        st.markdown(f"[{filename}, PDF page {page}](http://127.0.0.1:8000{citation['url']})")
        st.text(citation.get("excerpt", ""))
    with st.form("adjudication"):
        reviewer = st.text_input("Reviewer name")
        role = st.text_input("Professional role")
        scores = {criterion: st.selectbox(criterion.replace("_", " ").title(), ("unrated", "pass", "fail", "unclear"))
                  for criterion in CRITERIA}
        note = st.text_area("Notes, especially for a fail or unclear rating")
        submitted = st.form_submit_button("Save review")
    if submitted:
        if not reviewer.strip() or not role.strip() or "unrated" in scores.values():
            st.error("Enter a reviewer name, role, and all four ratings.")
        elif any(value != "pass" for value in scores.values()) and not note.strip():
            st.error("Add a note for any failed or unclear criterion.")
        else:
            decision = "pass" if all(value == "pass" for value in scores.values()) else "needs_revision"
            record({"case_id": selected["id"], "run_fingerprint": report["run_fingerprint"],
                    "reviewer": reviewer.strip(), "role": role.strip(),
                    "reviewed_at": datetime.now(timezone.utc).isoformat(), "ratings": scores,
                    "decision": decision, "note": note.strip()})
            st.success("Review saved locally.")


if __name__ == "__main__":
    main()
