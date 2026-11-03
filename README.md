# Afya Msaada

Local, early stage filovirus source review and question answering prototype. It imports the nine supplied PDFs into one versioned SQLite registry. Only approved PDF hashes enter search. An Ollama model selects relevant passages, drafts a short answer, and runs a separate support and relevance check. Failed checks produce a decline reason. These automated checks do not establish clinical correctness.

## Run locally

Requires Python 3.11+ and the packages in `apps/api/requirements.txt`. The PDFs are local and ignored by Git.

After cloning, copy the nine PDFs from `C:\Muthusi\ML\ebola-chatbot\data\` into `data\source-pdfs\`. The PDFs and generated SQLite database are intentionally absent from GitHub.

```powershell
python -m pip install -r apps/api/requirements.txt
python -m apps.api.afya.cli import
python -m apps.api.afya.cli restore-demo-approvals
python -m apps.api.afya.cli index
python -m apps.api.afya.cli sources
python -m uvicorn apps.api.afya.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Import stages new or changed PDFs. To approve a reviewed version for the local demo:

```powershell
python -m apps.api.afya.cli approve who-bundibugyo-public-health-advice-camp-settings-2026.pdf --reviewer "Reviewer name" --note "Reviewed PDF and public scope"
```

Use `revoke` with the same arguments to remove a document from search. The current local database has the nine identical PDF hashes carried forward from the earlier demo's user reported 2 November 2026 approval. The reviewer identity and authority remain unspecified. This local status is not an institutional release authorization.

## Check

```powershell
python -m pytest apps/api/tests -q
python -m evals.run
```

The evaluation report is written to ignored `evals/runs/latest.json`. It records behavior, concept phrase hits, and whether a seed anchor page was cited; these are mechanical screens, not medical accuracy scores. A qualified review of answers and cited PDFs is still required.

In the 3 November 2026 local run, 6 of 20 seed questions received answers and 14 declined. Three answers covered all expected concept phrases, and one cited the seed anchor page. The strict public scope declines procedural clinical questions, so these counts are not a clinical quality pass. The six questions shown in the user feedback screenshot were checked separately and now produce relevant cited answers, referrals, or clarification.

If unrelated globally installed pytest plugins conflict, set `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'` before running the tests.

## Current limits

Search combines keyword results with local Ollama embeddings when an index is available. The Ollama answer adapter and automated support check are implemented, but a robust claim-by-claim verifier, hosted model comparison, authenticated reviewer workbench, and release gate are not. Broad personal and procedural clinical questions decline or ask for clarification. Review actions are available only through the local CLI. The supplied source URLs are not verified. Live outbreak questions and personal medical advice decline.

See [architecture](docs/architecture.md) for the next steps.
