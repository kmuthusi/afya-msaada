"""Resolve short follow-ups from prior user questions only, never prior answers."""
import re


def resolve(question: str, history: list[str]) -> tuple[str, str | None]:
    if re.search(r"\b(ebola|marburg|bundibugyo)\b", question, re.I):
        return question, None
    if not re.search(r"\b(it|its|they|them|that disease)\b", question, re.I):
        return question, None
    recent = " ".join(history[-3:]).lower()
    names = [d for d in ("ebola", "marburg", "bundibugyo") if re.search(rf"\b{d}\b", recent)]
    if len(names) != 1:
        return question, "Which disease do you mean? Please name it in your question."
    return re.sub(r"\b(it|its|they|them|that disease)\b", names[0], question, flags=re.I), None
