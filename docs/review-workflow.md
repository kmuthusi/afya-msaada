# Clinical review workflow

Run `python -m evals.run` after importing and indexing sources. The output under `evals/runs/` is a draft packet with the question, generated response, decline reason, cited PDF page, expected concept phrase matches, and seed anchor page match. Mechanical matches are not approval.

For each response, a qualified reviewer should open the original PDF page and assess medical accuracy, source support, public clarity, and safety. Record the reviewer identity, role, date, notes, and a decision in a controlled review system. High risk cases need an independent second review. If a source hash, retrieval method, answer code, or case set changes, regenerate and review the packet. No release gate or authenticated review workbench is implemented yet, so this project cannot declare a clinical pass.
