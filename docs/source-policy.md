# Source policy for the local prototype

The source manifest records each PDF's original audience tier (`public`, `clinical`, or `restricted`), disease tags, and any known source URL. These tags do not grant approval. Import stores the exact SHA-256 version and stages it. An explicit reviewer action approves or revokes that version. A changed or missing PDF is automatically revoked before a chat search. Only approved versions appear in results.

The nine current PDFs were all marked approved in the earlier local demo after a user confirmation on 2 November 2026. Their byte hashes match the files in this workspace, so that status was carried into this local database. The approving person's identity and authority were not supplied. The `clinical` and `restricted` audience tags remain visible in the manifest. A health authority must decide whether those documents are appropriate for a public product.

Registering a new PDF adds metadata only. Import stages the exact file hash and extracts page-linked passages. A reviewer must approve that hash explicitly before search can use it. `rebuild-passages` changes the extraction of unchanged PDFs and preserves the exact-hash approval, but invalidates the embedding index until it is rebuilt.

Do not treat the source URL fields as verified links; most are empty. For any public deployment, check publisher, publication date, jurisdiction, intended audience, license, superseding guidance, and original URL, then record an accountable review decision.
