from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import core

app = FastAPI(title="Afya Msaada local prototype")


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    history: list[str] = Field(default_factory=list, max_length=3)


@app.get("/api/status")
def status():
    items = core.sources()
    return {"sources": len(items), "approved": sum(x["status"] == "approved" for x in items), "local_demo": True}


@app.get("/api/sources")
def sources():
    return core.sources()


@app.post("/api/chat")
def chat(req: ChatRequest):
    return core.answer(req.question, req.history)


@app.get("/api/pdfs/{filename}")
def pdf(filename: str):
    row = next((s for s in core.sources() if s["filename"] == filename), None)
    path = core.PDF_DIR / filename
    if row is None or row["status"] != "approved" or path.name != filename or not path.is_file() or core.digest(path) != row["sha256"]:
        raise HTTPException(status_code=404, detail="PDF unavailable")
    return FileResponse(path, media_type="application/pdf")


app.mount("/", StaticFiles(directory=core.ROOT / "apps/web", html=True), name="web")
