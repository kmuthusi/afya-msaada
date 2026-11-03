"""Answer model selection adapted from kenya-afya-bot's provider boundary.

Hosted use is opt-in. No patient summary is ever passed to these providers.
"""
import json
import os

from .ollama import chat_json as ollama_chat_json


def chat_json(system: str, user: str, *, max_tokens: int = 350) -> dict:
    provider = os.getenv("AFYA_LLM_PROVIDER", "ollama").strip().lower()
    if provider == "ollama":
        return ollama_chat_json(system, user, max_tokens=max_tokens)
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("AFYA_CHAT_MODEL", "")
        if not key or not model or model.startswith("llama"):
            raise ValueError("Set OPENAI_API_KEY and an OpenAI AFYA_CHAT_MODEL before hosted use")
        try:
            from openai import OpenAI

            response = OpenAI(api_key=key).chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                max_completion_tokens=max_tokens,
            )
        except Exception as exc:
            raise ValueError("Hosted model request failed") from exc
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Hosted model returned no JSON content")
        return json.loads(content)
    raise ValueError(f"Unsupported AFYA_LLM_PROVIDER: {provider}")
