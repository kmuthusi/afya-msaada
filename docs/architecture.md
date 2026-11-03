# Architecture and next steps

The current path is PDF import → SHA-256 version → SQLite page passages → approval → keyword and optional local Ollama semantic search → model evidence selection → model draft → separate support and relevance check → page citations or explicit decline. Source changes replace passages and reset approval. Revocation immediately removes passages from search. If Ollama is unavailable, the answer path declines.

Next: tune retrieval and reranking against expert labelled questions; compare local Ollama and a hosted provider; make model output structured claims; verify each claim independently against an approved passage. Add authenticated source review and clinical answer review with an audit trail and release gate. Keep public channels disabled until an accountable health authority approves them.
