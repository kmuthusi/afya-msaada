# Answer review workflow

1. Import and approve the current PDFs, run `python -m apps.api.afya.cli rebuild-passages` after processor changes, then run `python -m apps.api.afya.cli index`.
2. Generate `python -m evals.run --case-set review-seed-44`. The ignored report includes each question, answer or decline, citation, and source/code/model fingerprints.
3. Set a strong `AFYA_REVIEWER_PASSWORD`. Run `python -m streamlit run apps/reviewer/app.py --server.address 127.0.0.1` on the same machine as the API. For every case, inspect the original cited PDF page and rate medical accuracy, source support, public clarity, and safety. The workbench stores append-only review events in ignored `evals/reviews/clinical-adjudication.json`.
4. Have a second independent qualified reviewer assess every case. A failed or unclear rating needs a note and cannot pass the gate. Reviewer names and roles in this local workbench are self-reported and require institutional verification.
5. An accountable authority records a local `evals/reviews/authority-signoff.json` with `run_fingerprint`, `approver`, `role`, and `approved_at` after reviewing the packet and reviewer identities. Do not create this file on behalf of an unverified approver.
6. Run `python -m evals.readiness --strict`. Any source, code, case-set, model, or embedding change invalidates the review run.

The gate also checks all nine source versions and the embedding index. Even a passing local gate does not authorize a public release without institutional privacy, security, and clinical governance decisions.
