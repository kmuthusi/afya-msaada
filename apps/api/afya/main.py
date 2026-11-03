import hashlib
import hmac
import os
import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import core
from .patient.contract import ALLOWED_ROLES, TRUST_MARKER, validate

app = FastAPI(title="Afya Msaada local prototype")
_requests = defaultdict(deque)
_requests_lock = Lock()


def enforce_rate_limit(request: Request) -> None:
    window = 60
    maximum = int(os.getenv("AFYA_RATE_LIMIT_PER_MINUTE", "30"))
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _requests_lock:
        bucket = _requests[client]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= maximum:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    history: list[str] = Field(default_factory=list, max_length=3)


class ClinicianRequest(BaseModel):
    clinician_question: str = Field(min_length=2, max_length=1000)
    patient_summary: dict = Field(default_factory=dict)


@app.get("/api/status")
def status():
    items = core.sources()
    return {"sources": len(items), "approved": sum(x["status"] == "approved" for x in items),
            "index": core.index_status(), "local_demo": True}


@app.get("/api/health")
def health():
    return {"status": "up"}


@app.get("/api/ready")
def ready():
    from evals.readiness import check
    result = check()
    if not result["ready"]:
        raise HTTPException(status_code=503, detail=result)
    return result


@app.get("/api/sources")
def sources():
    return core.sources()


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    enforce_rate_limit(request)
    started = time.perf_counter()
    timings = {}
    result = core.answer(req.question, req.history, trace=timings)
    result["retrieval_trace"] = {
        "correlation_id": str(uuid.uuid4()),
        "question_hash": hashlib.sha256(req.question.encode("utf-8")).hexdigest()[:16],
        "source_fingerprint": core.source_fingerprint()[:16],
        "model_provider": os.getenv("AFYA_LLM_PROVIDER", "ollama"),
        "model": os.getenv("AFYA_CHAT_MODEL", "llama3.1:8b"),
        "source_count": len(result.get("citations", [])),
        "total_seconds": round(time.perf_counter() - started, 3),
        "timings": timings,
    }
    return result


@app.post("/api/clinician/query")
def clinician_query(
    req: ClinicianRequest,
    request: Request,
    x_api_key: str = Header(default=""),
    x_actor_claims_trust: str = Header(default=""),
    x_user_id: str = Header(default=""),
    x_facility: str = Header(default=""),
    x_user_role: str = Header(default=""),
    x_purpose_of_use: str = Header(default=""),
):
    enforce_rate_limit(request)
    configured = os.getenv("AFYA_CLINICIAN_API_KEY", "")
    if len(configured) < 16 or configured.casefold() in {"change-me-clinician-key", "local-dev-key", "test-token"} or not hmac.compare_digest(x_api_key, configured):
        raise HTTPException(status_code=401, detail="Private API authentication failed")
    if (x_actor_claims_trust != TRUST_MARKER or x_user_role not in ALLOWED_ROLES
            or x_purpose_of_use != "treatment" or not x_user_id or not x_facility):
        raise HTTPException(status_code=403, detail="Authenticated clinical actor claims are required")
    validation = validate(req.patient_summary, req.clinician_question)
    if validation["status"] != "accepted":
        return {"answer_status": validation["status"], "validation": validation, "answer": "", "sources": []}
    # The private contract is implemented, but patient-specific generation is gated.
    # No patient facts are sent to the answer model until clinical review is complete.
    return {"answer_status": "clinical_review_required", "validation": validation,
            "answer": "Patient-specific guidance is disabled pending clinical and privacy approval.",
            "sources": [], "patient_context_used": False}


@app.get("/api/pdfs/{filename}")
def pdf(filename: str):
    row = next((s for s in core.sources() if s["filename"] == filename), None)
    path = core.PDF_DIR / filename
    if row is None or row["status"] != "approved" or path.name != filename or not path.is_file() or core.digest(path) != row["sha256"]:
        raise HTTPException(status_code=404, detail="PDF unavailable")
    return FileResponse(path, media_type="application/pdf")


app.mount("/", StaticFiles(directory=core.ROOT / "apps/web", html=True), name="web")
