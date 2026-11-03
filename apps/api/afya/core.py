"""Local source registry, retrieval, and conservative extractive answering."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

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
    CREATE TABLE IF NOT EXISTS index_builds (
      model TEXT PRIMARY KEY, source_fingerprint TEXT NOT NULL,
      passage_count INTEGER NOT NULL, status TEXT NOT NULL, built_at TEXT NOT NULL
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
            from .sources.processor import extract
            count = 0
            for page, chunk in extract(path):
                con.execute("INSERT INTO passages(filename,sha256,page,text) VALUES(?,?,?,?)",
                            (path.name, sha, page, chunk))
                count += 1
            con.execute("INSERT INTO audit(at,action,filename,detail) VALUES(?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), "stage", path.name, sha))
            result.append({"filename": path.name, "status": "staged", "changed": True, "passages": count})
    return result


def rebuild_passages() -> dict:
    """Re-extract unchanged PDFs using the current processor; retain exact-hash approval."""
    from .sources.processor import extract
    result = {}
    with connect() as con:
        records = con.execute("SELECT filename,sha256 FROM sources ORDER BY filename").fetchall()
        for row in records:
            path = PDF_DIR / row["filename"]
            if not path.is_file() or digest(path) != row["sha256"]:
                raise ValueError(f"PDF hash mismatch: {row['filename']}")
            con.execute("DELETE FROM embeddings WHERE passage_id IN (SELECT id FROM passages WHERE filename=?)", (row["filename"],))
            con.execute("DELETE FROM passages WHERE filename=?", (row["filename"],))
            count = 0
            for page, chunk in extract(path):
                con.execute("INSERT INTO passages(filename,sha256,page,text) VALUES(?,?,?,?)",
                            (row["filename"], row["sha256"], page, chunk))
                count += 1
            con.execute("INSERT INTO audit(at,action,filename,detail) VALUES(?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), "rebuild_passages", row["filename"], str(count)))
            result[row["filename"]] = count
    return result


def sources() -> list[dict]:
    with connect() as con:
        return [dict(row) for row in con.execute("SELECT * FROM sources ORDER BY filename")]


def source_fingerprint() -> str:
    approved = [(row["filename"], row["sha256"], row["tier"], row["diseases"], row["source_url"])
                for row in sources() if row["status"] == "approved"]
    return hashlib.sha256(json.dumps(approved, sort_keys=True).encode("utf-8")).hexdigest()


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
    fingerprint = source_fingerprint()
    with connect() as con:
        total = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        con.execute("""INSERT INTO index_builds(model,source_fingerprint,passage_count,status,built_at)
          VALUES(?,?,?,?,?) ON CONFLICT(model) DO UPDATE SET source_fingerprint=excluded.source_fingerprint,
          passage_count=excluded.passage_count,status=excluded.status,built_at=excluded.built_at""",
          (model, fingerprint, total, "building", datetime.now(timezone.utc).isoformat()))
        rows = con.execute("""SELECT p.id,p.text FROM passages p LEFT JOIN embeddings e ON e.passage_id=p.id AND e.model=?
                              WHERE e.passage_id IS NULL ORDER BY p.id""", (model,)).fetchall()
    try:
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            vectors = embed([r["text"][:1800] for r in batch])
            with connect() as con:
                for row, vec in zip(batch, vectors):
                    con.execute("INSERT OR REPLACE INTO embeddings(passage_id,model,vector) VALUES(?,?,?)",
                                (row["id"], model, vec.tobytes()))
    except Exception:
        with connect() as con:
            con.execute("UPDATE index_builds SET status='failed' WHERE model=?", (model,))
        raise
    with connect() as con:
        actual = con.execute("SELECT COUNT(*) FROM embeddings WHERE model=?", (model,)).fetchone()[0]
        status = "ready" if actual == total and fingerprint == source_fingerprint() else "stale"
        con.execute("UPDATE index_builds SET status=?,passage_count=?,source_fingerprint=?,built_at=? WHERE model=?",
                    (status, actual, fingerprint, datetime.now(timezone.utc).isoformat(), model))
    return len(rows)


def index_status() -> dict:
    model = os.getenv("AFYA_EMBED_MODEL", "nomic-embed-text:latest")
    with connect() as con:
        row = con.execute("SELECT * FROM index_builds WHERE model=?", (model,)).fetchone()
        total = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        actual = con.execute("SELECT COUNT(*) FROM embeddings WHERE model=?", (model,)).fetchone()[0]
    if row is None:
        return {"status": "missing", "model": model, "passages": total, "embeddings": actual}
    ready = (row["status"] == "ready" and row["source_fingerprint"] == source_fingerprint()
             and row["passage_count"] == total and actual == total)
    return {"status": "ready" if ready else "stale", "model": model,
            "passages": total, "embeddings": actual, "built_at": row["built_at"]}


def semantic_search(question: str, limit: int = 20) -> list[dict]:
    model = os.getenv("AFYA_EMBED_MODEL", "nomic-embed-text:latest")
    if index_status()["status"] != "ready":
        return []
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


def resolve(question: str, history: list[str]) -> tuple[str, str | None]:
    from .conversation.context import resolve as resolve_context
    return resolve_context(question, history)


def contact_scenario(question: str) -> dict | None:
    """Describe the documented route without judging a particular handshake."""
    if not re.search(r"\b(shaking hands|handshake|handshaking|touching someone|touch someone)\b", question, re.I):
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
    activity = "handshake" if re.search(r"\b(shaking hands|handshake|handshaking)\b", question, re.I) else "touch"
    return {"status": "answered", "reason": "documented_transmission_route", "answer":
            f"The cited guidance describes {disease} transmission through direct or indirect contact with blood or other body fluids. I cannot determine from a particular {activity} alone whether that exposure occurred. If this relates to a real contact, seek advice from a local health service.",
            "citations": [citation], "resolved_question": question}


def ebola_overview(question: str) -> dict | None:
    if not re.fullmatch(r"\s*(?:tell me about|what is|explain|overview of)\s+ebola\s*[?.!]?\s*", question, re.I):
        return None
    with connect() as con:
        row = con.execute("""SELECT filename,page,page_text AS text,sha256 FROM (
          SELECT p.filename,p.page,GROUP_CONCAT(p.text, ' ') AS page_text,s.sha256 FROM passages p
          JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
          WHERE s.status='approved' GROUP BY p.filename,p.page
          ) WHERE page_text LIKE '%Ebola virus disease (EVD)%'
          AND page_text LIKE '%severe, and often fatal illness%'
          AND page_text LIKE '%contact with body secretions and fluids%'
          ORDER BY page LIMIT 1""").fetchone()
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


def bundibugyo_overview(question: str) -> dict | None:
    if not re.search(r"\b(what is|tell me about|define|explain)\b", question, re.I) or not re.search(r"\bbundibugyo\b", question, re.I):
        return None
    with connect() as con:
        row = con.execute("""SELECT p.filename,p.page,p.text,s.sha256 FROM passages p
          JOIN sources s ON s.filename=p.filename AND s.sha256=p.sha256
          WHERE s.status='approved' AND p.text LIKE '%Bundibugyo virus disease (BVD) is a severe%'
          ORDER BY p.page LIMIT 1""").fetchone()
    if row is None:
        return None
    passage = dict(row)
    start = passage["text"].find("Bundibugyo virus disease (BVD)")
    citation = {"filename": passage["filename"], "page": passage["page"], "sha256": passage["sha256"],
                "url": f"/api/pdfs/{quote(passage['filename'])}#page={passage['page']}",
                "excerpt": passage["text"][max(0, start):start + 450]}
    return {"status": "answered", "reason": "source_bound_definition",
            "answer": "Bundibugyo virus disease is a severe form of Ebola disease caused by Bundibugyo virus. The cited public-health document describes it as potentially fatal.",
            "citations": [citation], "resolved_question": question}


def answer(question: str, history: list[str] | None = None, trace: dict | None = None) -> dict:
    from .policy.guard import before_model, before_retrieval
    q, clarification = resolve(question.strip(), history or [])
    if clarification:
        return {"status": "clarify", "reason": "ambiguous_follow_up", "answer": clarification, "citations": [], "resolved_question": q}
    guarded = before_retrieval(q)
    if guarded:
        return {**guarded, "resolved_question": q}
    revoke_stale_sources()
    mortality = ebola_mortality(q)
    if mortality:
        return mortality
    bundibugyo = bundibugyo_overview(q)
    if bundibugyo:
        return bundibugyo
    overview = ebola_overview(q)
    if overview:
        return overview
    scenario = contact_scenario(q)
    if scenario:
        return scenario
    from .answering.public_summaries import answer as public_summary
    summary = public_summary(q)
    if summary:
        return summary
    guarded = before_model(q)
    if guarded:
        return {**guarded, "resolved_question": q}
    from .answering.pipeline import collect, draft_and_verify
    try:
        retrieval_started = time.perf_counter()
        candidates = collect(q)
        if trace is not None:
            trace["retrieval_seconds"] = round(time.perf_counter() - retrieval_started, 3)
            trace["candidate_count"] = len(candidates)
        model_started = time.perf_counter()
        grounded = draft_and_verify(q, candidates)
        if trace is not None:
            trace["model_and_check_seconds"] = round(time.perf_counter() - model_started, 3)
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return {"status": "declined", "reason": "model_or_verification_unavailable",
                "answer": "The answer model or verification step is unavailable. Please try again later or consult the source PDFs.",
                "citations": [], "resolved_question": q}
    if grounded is None:
        return {"status": "declined", "reason": "insufficient_verified_evidence", "answer": "I could not verify an answer to that question from the approved documents. Please check the source PDFs or ask a qualified health professional.", "citations": [], "resolved_question": q}
    response, pages = grounded
    if re.search(r"\b(risk assessment|classify|risk level)\b", q, re.I) and any("risk-assessment" in item["filename"] for item in pages):
        response += " This describes the cited 2026 assessment, not a current risk level."
    citations = [{"filename": item["filename"], "page": item["page"], "sha256": item["sha256"],
                  "url": f"/api/pdfs/{quote(item['filename'])}#page={item['page']}", "excerpt": item["text"][:500]}
                 for item in pages]
    return {"status": "answered", "reason": "verified_source_answer", "answer": response, "citations": citations, "resolved_question": q}
