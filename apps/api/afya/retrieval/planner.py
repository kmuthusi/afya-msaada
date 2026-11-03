"""Filovirus question plans adapted from kenya-afya-bot's evidence registry pattern.

Plans identify information needed for an answer. They do not encode medical answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceNeed:
    name: str
    terms: tuple[str, ...]
    query: str


@dataclass(frozen=True)
class EvidencePlan:
    name: str
    needs: tuple[EvidenceNeed, ...]


def plan(question: str) -> EvidencePlan | None:
    q = question.casefold()
    if re.search(r"\b(spread|transmit|contact|shaking hands|handshake)\b", q):
        needs = [EvidenceNeed("route", ("body fluids", "blood", "human-to-human transmission"),
                              "human-to-human transmission direct contact blood body fluids")]
        if re.search(r"\b(before symptoms|without symptoms|asymptomatic|infectious period)\b", q):
            needs.append(EvidenceNeed("timing", ("communicability period", "symptoms", "symptom onset"),
                                      "communicability period symptom onset transmission"))
        return EvidencePlan("transmission", tuple(needs))
    if re.search(r"\b(deadly|fatal|mortality|death rate|surviv\w*)\b", q):
        return EvidencePlan("outcomes", (EvidenceNeed("outcome", ("case fatality", "mortality", "fatal"),
                                                    "case fatality mortality outcomes"),))
    if re.search(r"\b(tell me about|overview|what is|explain)\b", q):
        return EvidencePlan("overview", (EvidenceNeed("definition", ("is a", "is an", "disease"),
                                                     "disease definition clinical overview"),))
    return None


def queries(question: str, evidence_plan: EvidencePlan | None) -> list[str]:
    found = [question]
    if evidence_plan:
        disease = next((name for name in ("Ebola", "Marburg", "Bundibugyo")
                        if re.search(rf"\b{name}\b", question, re.I)), "")
        found.extend(f"{disease} {need.query}".strip() for need in evidence_plan.needs)
    return list(dict.fromkeys(found))


def coverage(evidence_plan: EvidencePlan | None, passages: list[dict]) -> dict:
    if evidence_plan is None:
        return {"plan": None, "required": [], "covered": [], "missing": [], "complete": True}
    text = " ".join(str(item.get("text", "")).casefold() for item in passages)
    required = [need.name for need in evidence_plan.needs]
    covered = [need.name for need in evidence_plan.needs if any(term in text for term in need.terms)]
    missing = [name for name in required if name not in covered]
    return {"plan": evidence_plan.name, "required": required, "covered": covered,
            "missing": missing, "complete": not missing}
