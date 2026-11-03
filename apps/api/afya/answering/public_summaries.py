"""Short public overviews anchored to specific approved document passages."""
from __future__ import annotations

import re
from urllib.parse import quote

from .. import core


_OVERVIEWS = (
    (
        r"(?:ebola(?: case)? isolation(?: guidance)?|(?:what is|explain) ebola(?: case)? isolation|how are ebola (?:cases|patients) isolated)",
        "ipc-ebola-marburg-2026.pdf", 17,
        "Patients with suspected or confirmed Ebola disease (EBOD) or Marburg disease (MARD) should be isolated",
        "The cited 2026 guidance says patients with suspected or confirmed Ebola disease should be isolated in a health-care setting, preferably in a single-patient room, with appropriate protection for health workers. The facility's clinical and public-health teams determine the detailed procedure.",
        "source_bound_isolation_overview",
    ),
    (
        r"(?:ebola treatment|treatment for ebola|how is ebola treated|what is the treatment for ebola)",
        "diagnostic-testing-ebola-marburg-2026.pdf", 12,
        "early diagnosis, optimized supportive care and targeted therapeutics",
        "The cited 2026 guidance describes early diagnosis and supportive care as important for Ebola outcomes. Targeted treatments may apply to particular Ebola viruses; a qualified clinical team must identify the virus and decide on care. If this concerns a real illness, seek prompt medical attention.",
        "source_bound_treatment_overview",
    ),
    (
        r"(?:ebola vaccine|is there an? ebola vaccine|(?:what|which) vaccine (?:is available )?for ebola)",
        "who-bundibugyo-public-health-advice-camp-settings-2026.pdf", 7,
        "There is currently no licensed vaccine against BDBV",
        "The cited 2026 WHO document distinguishes Ebola virus disease, for which it describes an approved vaccine, from Bundibugyo virus disease, for which it reported no licensed vaccine. Vaccine availability and eligibility must be checked with the relevant health authority for the specific virus and location.",
        "source_bound_vaccine_overview",
    ),
)


def answer(question: str) -> dict | None:
    normalized = re.sub(r"\s+", " ", question.strip().rstrip("?.!")).casefold()
    for pattern, filename, page, marker, summary, reason in _OVERVIEWS:
        if not re.fullmatch(pattern, normalized):
            continue
        with core.connect() as con:
            row = con.execute("""SELECT p.text,s.sha256 FROM passages p
                JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
                WHERE s.status='approved' AND p.filename=? AND p.page=? AND p.text LIKE ?
                LIMIT 1""", (filename, page, f"%{marker}%")).fetchone()
        if row is None:
            return None
        passage = row["text"]
        start = max(0, passage.casefold().find(marker.casefold()) - 60)
        citation = {"filename": filename, "page": page, "sha256": row["sha256"],
                    "url": f"/api/pdfs/{quote(filename)}#page={page}",
                    "excerpt": passage[start:start + 500]}
        return {"status": "answered", "reason": reason, "answer": summary,
                "citations": [citation], "resolved_question": question}
    return None
