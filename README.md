# Afya Msaada

Local filovirus guidance prototype. Its component layout adapts the implementation pattern in `C:\Muthusi\ML\kenya-afya-bot` to the nine Ebola and Marburg PDFs. Only approved PDF hashes enter search. The public answer path uses evidence planning, hybrid retrieval, a model draft, and a separate support check. These automated checks do not establish clinical correctness.

## Run locally

Requires Python 3.11+ and the packages in `apps/api/requirements.txt`. The PDFs are local and ignored by Git.

After cloning, copy the nine PDFs from `C:\Muthusi\ML\ebola-chatbot\data\` into `data\source-pdfs\`. The PDFs and generated SQLite database are intentionally absent from GitHub.

```powershell
python -m pip install -r apps/api/requirements.txt
python -m apps.api.afya.cli import
python -m apps.api.afya.cli restore-demo-approvals
python -m apps.api.afya.cli index
python -m apps.api.afya.cli sources
python -m infra.preflight
python -m uvicorn apps.api.afya.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Import stages new or changed PDFs. To approve a reviewed version for the local demo:

```powershell
python -m apps.api.afya.cli approve who-bundibugyo-public-health-advice-camp-settings-2026.pdf --reviewer "Reviewer name" --note "Reviewed PDF and public scope"
```

Use `revoke` with the same arguments to remove a document from search. The current local database has the nine identical PDF hashes carried forward from the earlier demo's user reported 2 November 2026 approval. The reviewer identity and authority remain unspecified. This local status is not an institutional release authorization.

To add a source, register its metadata, copy the PDF into `data/source-pdfs`, import it, review it, and then rebuild the index:

```powershell
python -m apps.api.afya.cli register new-guidance.pdf --tier public --disease Ebola --source-url https://publisher.example/guidance
python -m apps.api.afya.cli import
python -m apps.api.afya.cli approve new-guidance.pdf --reviewer "Reviewer name" --note "Reviewed this exact PDF version"
python -m apps.api.afya.cli index
```

`rebuild-passages` re-extracts unchanged approved PDFs after document-processing changes; run `index` afterward. Changed PDF bytes still require a new approval.

The private `/api/clinician/query` boundary requires `AFYA_CLINICIAN_API_KEY` and authenticated actor claims. It validates a minimal patient summary but deliberately does not generate patient-specific advice. Use it only behind a trusted EMR proxy on a private network.

## Check

```powershell
python -m pytest apps/api/tests -q
python -m evals.run
python -m evals.run --case-set review-seed-44
python -m evals.readiness --strict
```

Evaluation reports are written to ignored `evals/runs/`. They record behavior, concept phrase hits, case and code fingerprints, and cited pages; these are mechanical screens, not medical accuracy scores. Run the local review workbench with a strong `AFYA_REVIEWER_PASSWORD` and `python -m streamlit run apps/reviewer/app.py --server.address 127.0.0.1`. The release gate fails until two qualified reviews per case and an accountable authority signoff are recorded.

The earlier 3 November 2026 baseline answered 6 of 20 seed questions and declined 14. Three answers covered all expected concept phrases. This baseline predates the adapted document processor and evidence planner and is not a clinical quality pass. The six questions shown in user feedback were checked separately and produce cited answers, referrals, or clarification.

The current 44-case review packet answered 11, declined 31, and requested clarification on 2. Every answered case has a page citation. These counts describe routing behavior only; no clinician has rated the answers.

If unrelated globally installed pytest plugins conflict, set `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'` before running the tests.

## Current limits

Search combines keyword results with Ollama embeddings when the current index is ready. The answer provider is local Ollama by default; OpenAI is an opt-in hosted adapter using `AFYA_LLM_PROVIDER=openai`, an explicit `AFYA_CHAT_MODEL`, and `OPENAI_API_KEY`. Hosted use may send approved source excerpts and questions to that provider. The reviewer workbench is local and password gated, but reviewer identity is self-reported. Claim-by-claim clinical verification, institutional authentication, privacy approval, and release authorization remain outstanding. Broad personal and procedural clinical questions decline or ask for clarification.

See [architecture](docs/architecture.md) for the next steps.
