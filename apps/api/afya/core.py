"""Local source registry, retrieval, and conservative extractive answering."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from pypdf import PdfReader
import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DB = Path(os.getenv("AFYA_DB", ROOT / "data/afya.sqlite3"))
PDF_DIR = Path(os.getenv("AFYA_PDF_DIR", ROOT / "data/source-pdfs"))
MANIFEST = ROOT / "data/source-manifest.json"
STOP = set("a an and are can do for from how in is it of on or the to what when where which who why with you your about".split())
DISEASES = {"ebola", "marburg", "bundibugyo", "filovirus"}


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS sources (
      filename TEXT PRIMARY KEY, sha256 TEXT NOT NULL, tier TEXT NOT NULL,
      diseases TEXT NOT NULL, status TEXT NOT NULL, reviewed_by TEXT,
      reviewed_at TEXT, note TEXT, source_url TEXT
    );
    CREATE TABLE IF NOT EXISTS passages (
      id INTEGER PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL,
      page INTEGER NOT NULL, text TEXT NOT NULL,
      FOREIGN KEY(filename) REFERENCES sources(filename)
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(text, content='passages', content_rowid='id');
    CREATE TRIGGER IF NOT EXISTS passage_ai AFTER INSERT ON passages BEGIN
      INSERT INTO passages_fts(rowid,text) VALUES(new.id,new.text);
    END;
    CREATE TRIGGER IF NOT EXISTS passage_ad AFTER DELETE ON passages BEGIN
      INSERT INTO passages_fts(passages_fts,rowid,text) VALUES('delete',old.id,old.text);
    END;
    CREATE TABLE IF NOT EXISTS audit (
      id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL,
      filename TEXT NOT NULL, actor TEXT, detail TEXT
    );
    CREATE TABLE IF NOT EXISTS embeddings (
      passage_id INTEGER PRIMARY KEY, model TEXT NOT NULL, vector BLOB NOT NULL,
      FOREIGN KEY(passage_id) REFERENCES passages(id) ON DELETE CASCADE
    );
    """)
    return con


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def manifest() -> dict:
    return {x["filename"]: x for x in json.loads(MANIFEST.read_text(encoding="utf-8"))}


def ingest() -> list[dict]:
    """Version by hash; changed files lose approval before new text is searchable."""
    known = manifest()
    result = []
    with connect() as con:
        for path in sorted(PDF_DIR.glob("*.pdf")):
            if path.name not in known:
                continue
            sha = digest(path)
            old = con.execute("SELECT sha256,status FROM sources WHERE filename=?", (path.name,)).fetchone()
            if old and old["sha256"] == sha:
                result.append({"filename": path.name, "status": old["status"], "changed": False})
                continue
            item = known[path.name]
            con.execute("DELETE FROM embeddings WHERE passage_id IN (SELECT id FROM passages WHERE filename=?)", (path.name,))
            con.execute("DELETE FROM passages WHERE filename=?", (path.name,))
            con.execute("""INSERT INTO sources(filename,sha256,tier,diseases,status,source_url)
              VALUES(?,?,?,?,?,?) ON CONFLICT(filename) DO UPDATE SET
              sha256=excluded.sha256,tier=excluded.tier,diseases=excluded.diseases,
              status='staged',reviewed_by=NULL,reviewed_at=NULL,note=NULL,source_url=excluded.source_url""",
              (path.name, sha, item["tier"], json.dumps(item["diseases"]), "staged", item.get("source_url")))
            reader = PdfReader(path)
            count = 0
            for page, obj in enumerate(reader.pages, 1):
                raw = re.sub(r"\s+", " ", obj.extract_text() or "").strip()
                if not raw:
                    continue
                # Overlap keeps sentences near page segment boundaries recoverable.
                for start in range(0, len(raw), 1250):
                    chunk = raw[max(0, start - 120):start + 1500]
                    if len(chunk) < 80:
                        continue
                    con.execute("INSERT INTO passages(filename,sha256,page,text) VALUES(?,?,?,?)",
                                (path.name, sha, page, chunk))
                    count += 1
            con.execute("INSERT INTO audit(at,action,filename,detail) VALUES(?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), "stage", path.name, sha))
            result.append({"filename": path.name, "status": "staged", "changed": True, "passages": count})
    return result


def sources() -> list[dict]:
    with connect() as con:
        return [dict(row) for row in con.execute("SELECT * FROM sources ORDER BY filename")]


def revoke_stale_sources() -> list[str]:
    """Fail closed when a reviewed PDF changed or disappeared since import."""
    stale = []
    with connect() as con:
        rows = con.execute("SELECT filename,sha256 FROM sources WHERE status='approved'").fetchall()
        for row in rows:
            path = PDF_DIR / row["filename"]
            if not path.is_file() or digest(path) != row["sha256"]:
                stale.append(row["filename"])
                now = datetime.now(timezone.utc).isoformat()
                con.execute("UPDATE sources SET status='revoked',reviewed_at=?,note=? WHERE filename=?",
                            (now, "Local PDF changed or disappeared", row["filename"]))
                con.execute("INSERT INTO audit(at,action,filename,detail) VALUES(?,?,?,?)",
                            (now, "auto_revoke", row["filename"], "PDF hash mismatch or missing file"))
    return stale


def change_status(filename: str, action: str, reviewer: str, note: str) -> dict:
    if action not in {"approve", "revoke"}:
        raise ValueError("Unknown action")
    if not reviewer.strip() or not note.strip():
        raise ValueError("Reviewer and note are required")
    with connect() as con:
        row = con.execute("SELECT * FROM sources WHERE filename=?", (filename,)).fetchone()
        if row is None:
            raise ValueError("Source not imported")
        if action == "approve" and (row["status"] != "staged" or digest(PDF_DIR / filename) != row["sha256"]):
            raise ValueError("Only the current staged version can be approved")
        status = "approved" if action == "approve" else "revoked"
        now = datetime.now(timezone.utc).isoformat()
        con.execute("UPDATE sources SET status=?,reviewed_by=?,reviewed_at=?,note=? WHERE filename=?",
                    (status, reviewer, now, note, filename))
        con.execute("INSERT INTO audit(at,action,filename,actor,detail) VALUES(?,?,?,?,?)",
                    (now, action, filename, reviewer, note))
        return {"filename": filename, "status": status}


def terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    return list(dict.fromkeys(w for w in words if len(w) > 2 and w not in STOP))[:12]


def embed(texts: list[str]) -> list[np.ndarray]:
    url = os.getenv("AFYA_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/embed"
    model = os.getenv("AFYA_EMBED_MODEL", "nomic-embed-text:latest")
    response = httpx.post(url, json={"model": model, "input": texts}, timeout=180)
    response.raise_for_status()
    return [np.asarray(v, dtype=np.float32) for v in response.json()["embeddings"]]


def index_embeddings(batch_size: int = 32) -> int:
    model = os.getenv("AFYA_EMBED_MODEL", "nomic-embed-text:latest")
    with connect() as con:
        rows = con.execute("""SELECT p.id,p.text FROM passages p LEFT JOIN embeddings e ON e.passage_id=p.id AND e.model=?
                              WHERE e.passage_id IS NULL ORDER BY p.id""", (model,)).fetchall()
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        vectors = embed([r["text"][:1800] for r in batch])
        with connect() as con:
            for row, vec in zip(batch, vectors):
                con.execute("INSERT OR REPLACE INTO embeddings(passage_id,model,vector) VALUES(?,?,?)",
                            (row["id"], model, vec.tobytes()))
    return len(rows)


def semantic_search(question: str, limit: int = 20) -> list[dict]:
    model = os.getenv("AFYA_EMBED_MODEL", "nomic-embed-text:latest")
    with connect() as con:
        rows = con.execute("""SELECT p.filename,p.page,p.text,s.sha256,s.tier,e.vector FROM embeddings e
                 JOIN passages p ON p.id=e.passage_id JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
                 WHERE s.status='approved' AND e.model=?""", (model,)).fetchall()
    if not rows:
        return []
    query = embed([question])[0]
    query /= max(float(np.linalg.norm(query)), 1e-9)
    scored = []
    named = set(terms(question)) & DISEASES
    for row in rows:
        item = dict(row)
        vec = np.frombuffer(item.pop("vector"), dtype=np.float32)
        if len(vec) != len(query):
            continue
        if named and not all(d in (item["filename"] + " " + item["text"]).lower() for d in named):
            continue
        score = float(np.dot(query, vec) / max(float(np.linalg.norm(vec)), 1e-9))
        item["semantic_score"] = score
        scored.append(item)
    scored.sort(key=lambda x: x["semantic_score"], reverse=True)
    return scored[:limit]


def search(question: str, limit: int = 6) -> list[dict]:
    words = terms(question)
    if not words:
        return []
    query = " OR ".join(f'"{w}"' for w in words)
    with connect() as con:
        rows = con.execute("""SELECT p.filename,p.page,p.text,s.sha256,s.tier,
              bm25(passages_fts) AS rank FROM passages_fts
              JOIN passages p ON p.id=passages_fts.rowid
              JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
              WHERE passages_fts MATCH ? AND s.status='approved'
              ORDER BY rank LIMIT 250""", (query,)).fetchall()
    named = set(words) & DISEASES
    scored = []
    for row in rows:
        item = dict(row)
        if named and not any(d in (item["filename"] + " " + item["text"]).lower() for d in named):
            continue
        hits = sum(w in item["text"].lower() for w in words)
        item["score"] = hits / len(words)
        if hits >= min(2, len(words)):
            scored.append(item)
    scored.sort(key=lambda x: (-x["score"], x["rank"]))
    seen = set()
    out = []
    for item in scored:
        key = (item["filename"], item["page"])
        if key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return out


def best_excerpt(question: str, evidence: list[dict]) -> tuple[dict, str, float] | None:
    words = terms(question)
    named = set(words) & DISEASES
    definition = bool(re.match(r"\s*(what is|define|explain)\b", question, re.I))
    options = []
    for item in evidence:
        for sentence in re.split(r"(?<=[.!?])\s+", item["text"]):
            s = sentence.strip(" \t•�")
            if not 45 <= len(s) <= 370 or "http" in s.lower():
                continue
            low = s.lower()
            if named and not all(re.search(rf"\b{re.escape(d)}\b", low) for d in named):
                continue
            coverage = sum(bool(re.search(rf"\b{re.escape(w)}\b", low)) for w in words) / len(words)
            score = coverage
            if definition and re.search(r"\b(is a|is an|refers to|is caused by)\b", low):
                score += .3
            if re.search(r"\b(references|bibliography|table of contents)\b", low):
                score -= .4
            if "public-health-advice" in item["filename"]:
                score += .04
            options.append((score, item, s, coverage))
    if not options:
        return None
    options.sort(key=lambda x: x[0], reverse=True)
    _, item, sentence, coverage = options[0]
    return item, sentence, coverage


def resolve(question: str, history: list[str]) -> tuple[str, str | None]:
    if not re.search(r"\b(it|its|they|them|that disease)\b", question, re.I):
        return question, None
    recent = " ".join(history[-3:]).lower()
    names = [d for d in ("ebola", "marburg", "bundibugyo") if re.search(rf"\b{d}\b", recent)]
    if len(names) != 1:
        return question, "Which disease do you mean? Please name it in your question."
    return re.sub(r"\b(it|its|they|them|that disease)\b", names[0], question, flags=re.I), None


def contact_scenario(question: str) -> dict | None:
    """Describe the documented route without judging a particular handshake."""
    if not re.search(r"\b(shaking hands|handshake|handshaking)\b", question, re.I):
        return None
    match = re.search(r"\b(ebola|marburg)\b", question, re.I)
    if not match:
        return None
    with connect() as con:
        row = con.execute("""SELECT p.filename,p.page,p.text,s.sha256 FROM passages p
          JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
          WHERE s.status='approved' AND p.text LIKE ? ORDER BY p.page LIMIT 1""",
          ("%Human-to-human transmission occurs via exposure to blood and other body fluids%",)).fetchone()
    if row is None:
        return None
    passage = dict(row)
    disease = match.group(1).capitalize()
    citation = {"filename": passage["filename"], "page": passage["page"], "sha256": passage["sha256"],
                "url": f"/api/pdfs/{quote(passage['filename'])}#page={passage['page']}",
                "excerpt": passage["text"][:500]}
    return {"status": "answered", "reason": "documented_transmission_route", "answer":
            f"The cited guidance describes {disease} transmission through direct or indirect contact with blood or other body fluids. I cannot determine from a handshake alone whether that exposure occurred. If this relates to a real contact, seek advice from a local health service.",
            "citations": [citation], "resolved_question": question}


def ebola_overview(question: str) -> dict | None:
    if not re.fullmatch(r"\s*(?:tell me about|what is|explain|overview of)\s+ebola\s*[?.!]?\s*", question, re.I):
        return None
    with connect() as con:
        row = con.execute("""SELECT p.filename,p.page,p.text,s.sha256 FROM passages p
          JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
          WHERE s.status='approved' AND p.text LIKE '%Ebola virus disease (EVD)%'
          AND p.text LIKE '%severe, and often fatal illness%'
          AND p.text LIKE '%contact with body secretions and fluids%'
          ORDER BY p.page LIMIT 1""").fetchone()
    if row is None:
        return None
    passage = dict(row)
    citation = {"filename": passage["filename"], "page": passage["page"], "sha256": passage["sha256"],
                "url": f"/api/pdfs/{quote(passage['filename'])}#page={passage['page']}",
                "excerpt": passage["text"][max(0, passage["text"].find("Ebola virus disease (EVD)") - 30):][:550]}
    return {"status": "answered", "reason": "source_bound_overview",
            "answer": "Ebola virus disease is a severe illness that can be fatal. The cited Kenya case-management guideline describes spread between people through contact with body secretions and fluids. Would you like to know about symptoms, transmission, or care guidance?",
            "citations": [citation], "resolved_question": question}


def ebola_mortality(question: str) -> dict | None:
    if not re.search(r"\b(ebola)\b", question, re.I) or not re.search(r"\b(deadly|fatal|mortality|death rate)\b", question, re.I):
        return None
    with connect() as con:
        row = con.execute("""SELECT p.filename,p.page,p.text,s.sha256 FROM passages p
          JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
          WHERE s.status='approved' AND p.text LIKE '%EVD outbreaks have a case fatality rate ranging from 25% to 90%'
          ORDER BY p.page LIMIT 1""").fetchone()
    if row is None:
        return None
    passage = dict(row)
    start = passage["text"].find("EVD outbreaks have a case fatality rate")
    citation = {"filename": passage["filename"], "page": passage["page"], "sha256": passage["sha256"],
                "url": f"/api/pdfs/{quote(passage['filename'])}#page={passage['page']}",
                "excerpt": passage["text"][max(0, start - 80):start + 250]}
    return {"status": "answered", "reason": "source_bound_mortality_summary",
            "answer": "The cited Kenya guideline reports Ebola outbreak case fatality rates ranging from 25% to 90%, with an average of about 50%. Those outbreak figures cannot predict an individual's outcome.",
            "citations": [citation], "resolved_question": question}


def answer(question: str, history: list[str] | None = None) -> dict:
    q, clarification = resolve(question.strip(), history or [])
    if clarification:
        return {"status": "clarify", "reason": "ambiguous_follow_up", "answer": clarification, "citations": [], "resolved_question": q}
    if re.search(r"\b(today|now|current|latest|live|this week)\b", q, re.I):
        return {"status": "declined", "reason": "current_information_unavailable", "answer": "I cannot verify current outbreak information from this local document collection. Check the relevant health authority's latest update.", "citations": [], "resolved_question": q}
    if re.search(r"\b(i|my|me|we|our)\b", q, re.I) and re.search(r"\b(exposed|symptoms|sick|infected|diagnos\w*|treat\w*|isolat\w*|suspect|have\s+(?:ebola|marburg)|will\s+i\s+die)\b", q, re.I):
        return {"status": "declined", "reason": "personal_medical_advice", "answer": "I cannot assess whether you have Ebola or predict your outcome. If you suspect infection or have concerning symptoms, seek prompt advice from a qualified local health service and follow its instructions.", "citations": [], "resolved_question": q}
    if re.search(r"\b(?:dose|dosage|how much medicine)\b", q, re.I):
        return {"status": "declined", "reason": "individual_treatment_request", "answer": "I cannot recommend a medicine or dose. Please ask a qualified clinician.", "citations": [], "resolved_question": q}
    if re.search(r"\b(?:case management|clinical management)\b", q, re.I) and not re.search(r"\b(?:symptoms|testing|triage|treatment|fluids|infection prevention)\b", q, re.I):
        return {"status": "clarify", "reason": "broad_clinical_guidance", "answer": "Which part of case management do you mean? The supplied guidelines cover many clinical and facility procedures. Please name the topic and whether you need a public explanation or professional guidance.", "citations": [], "resolved_question": q}
    revoke_stale_sources()
    mortality = ebola_mortality(q)
    if mortality:
        return mortality
    overview = ebola_overview(q)
    if overview:
        return overview
    scenario = contact_scenario(q)
    if scenario:
        return scenario
    if re.search(r"\b(specimen|assay|intravenous|resuscitation|PPE|protective equipment|isolat\w*|diagnos\w*|clinical guideline|IPC guideline|laboratory testing|medication|therapy)\b", q, re.I):
        return {"status": "declined", "reason": "professional_clinical_guidance", "answer": "This asks for clinical or infection-control guidance that needs a qualified professional and the full current protocol. I cannot safely summarize it for an individual in this public chat prototype.", "citations": [], "resolved_question": q}
    from .answering.pipeline import collect, draft_and_verify
    try:
        grounded = draft_and_verify(q, collect(q))
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        grounded = None
    if grounded is None:
        return {"status": "declined", "reason": "insufficient_verified_evidence", "answer": "I could not verify an answer to that question from the approved documents. Please check the source PDFs or ask a qualified health professional.", "citations": [], "resolved_question": q}
    response, pages = grounded
    citations = [{"filename": item["filename"], "page": item["page"], "sha256": item["sha256"],
                  "url": f"/api/pdfs/{quote(item['filename'])}#page={item['page']}", "excerpt": item["text"][:500]}
                 for item in pages]
    return {"status": "answered", "reason": "verified_source_answer", "answer": response, "citations": citations, "resolved_question": q}
