"""Minimum necessary patient summary validation for a private EMR boundary."""
from __future__ import annotations

import re
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Any


FORBIDDEN_KEYS = {"name", "first_name", "last_name", "full_name", "phone", "email", "address",
                  "national_id", "patient_id", "medical_record_number", "date_of_birth", "dob", "identifier"}
ALLOWED_ROLES = {"doctor", "nurse", "clinical_officer"}
TRUST_MARKER = "emr_access_token_authenticated"
SECTION_FIELDS = {
    "patient": {"age_years", "age_group", "sex", "pregnant_or_breastfeeding"},
    "encounter": {"date"},
    "exposure": {"type", "date"},
    "symptoms": {"status", "onset_date"},
}


def _keys(value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).casefold()
            yield from _keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _keys(nested)


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def validate(summary: object, question: str) -> dict:
    if not isinstance(summary, dict):
        return {"status": "rejected", "errors": ["patient_summary must be an object"], "missing": []}
    forbidden = sorted(set(_keys(summary)) & FORBIDDEN_KEYS)
    if forbidden:
        return {"status": "rejected", "errors": [f"Direct identifier fields are not allowed: {', '.join(forbidden)}"], "missing": []}
    if len(json.dumps(summary)) > 8192:
        return {"status": "rejected", "errors": ["patient_summary exceeds size limit"], "missing": []}
    allowed_sections = set(SECTION_FIELDS)
    unknown = set(summary) - allowed_sections
    if unknown:
        return {"status": "rejected", "errors": [f"Unknown patient_summary sections: {', '.join(sorted(unknown))}"], "missing": []}
    for section in allowed_sections & set(summary):
        if not isinstance(summary[section], dict):
            return {"status": "rejected", "errors": [f"{section} must be an object"], "missing": []}
        unknown_fields = set(summary[section]) - SECTION_FIELDS[section]
        if unknown_fields:
            return {"status": "rejected", "errors": [f"Unknown fields in {section}: {', '.join(sorted(unknown_fields))}"], "missing": []}
    patient = summary.get("patient", {})
    encounter = summary.get("encounter", {})
    exposure = summary.get("exposure", {})
    symptoms = summary.get("symptoms", {})
    errors = []
    missing = []
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    if patient.get("age_group") and patient["age_group"] not in {"infant", "child", "adolescent", "adult", "older_adult", "unknown"}:
        errors.append("age_group is not a supported value")
    if patient.get("sex") and patient["sex"] not in {"female", "male", "intersex", "unknown"}:
        errors.append("sex is not a supported value")
    if patient.get("pregnant_or_breastfeeding") not in {None, True, False, "unknown"}:
        errors.append("pregnant_or_breastfeeding is not a supported value")
    if exposure.get("type") and exposure["type"] not in {"direct_contact", "body_fluids", "needlestick", "healthcare", "uncertain"}:
        errors.append("exposure type is not a supported value")
    age = patient.get("age_years")
    if age is None and not patient.get("age_group"):
        missing.append("patient age or age group")
    elif age is not None and (not isinstance(age, (int, float)) or isinstance(age, bool) or not 0 <= age <= 120):
        errors.append("age_years must be between 0 and 120")
    encounter_date = _date(encounter.get("date"))
    if encounter_date is None:
        missing.append("encounter date in ISO format")
    elif encounter_date > today:
        errors.append("encounter date cannot be in the future")
    elif (today - encounter_date).days > 30:
        missing.append("current encounter date within 30 days")
    if re.search(r"\b(exposure|contact|touch|shaking hands)\b", question, re.I):
        if not exposure.get("type"):
            missing.append("exposure type")
        exposure_date = _date(exposure.get("date"))
        if exposure_date is None:
            missing.append("exposure date in ISO format")
        elif exposure_date > today:
            errors.append("exposure date cannot be in the future")
    if re.search(r"\b(symptom|fever|bleeding|sick)\b", question, re.I):
        if symptoms.get("status") not in {"present", "absent", "unknown"}:
            missing.append("symptom status")
        if symptoms.get("status") == "present" and _date(symptoms.get("onset_date")) is None:
            missing.append("symptom onset date")
        if symptoms.get("status") == "absent" and symptoms.get("onset_date"):
            errors.append("symptom status and onset date conflict")
        onset = _date(symptoms.get("onset_date"))
        if onset and onset > today:
            errors.append("symptom onset date cannot be in the future")
    if errors:
        status = "rejected"
    elif missing:
        status = "needs_clarification"
    else:
        status = "accepted"
    return {"status": status, "errors": errors, "missing": list(dict.fromkeys(missing))}
