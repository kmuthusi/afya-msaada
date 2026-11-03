"""Small local chat model adapter. The caller supplies the task and evidence."""
import json
import os

import httpx


def chat_json(system: str, user: str, *, max_tokens: int = 350) -> dict:
    endpoint = os.getenv("AFYA_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    model = os.getenv("AFYA_CHAT_MODEL", "llama3.1:8b")
    response = httpx.post(
        endpoint,
        json={
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=120,
    )
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"])
