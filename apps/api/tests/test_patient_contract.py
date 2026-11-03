from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from apps.api.afya.main import app
from apps.api.afya.patient.contract import validate


TODAY = datetime.now(ZoneInfo("Africa/Nairobi")).date()


def test_patient_summary_rejects_identifiers_and_unknown_fields():
    assert validate({"patient": {"name": "Jane Doe"}}, "Ebola exposure")["status"] == "rejected"
    assert validate({"patient": {"notes": "free text"}}, "Ebola exposure")["status"] == "rejected"


def test_patient_summary_needs_critical_exposure_facts():
    result = validate({"patient": {"age_group": "adult"}, "encounter": {"date": TODAY.isoformat()}},
                      "How should an Ebola exposure be assessed?")
    assert result["status"] == "needs_clarification"
    assert "exposure type" in result["missing"]


def test_patient_summary_rejects_contradictory_symptoms():
    result = validate({"patient": {"age_group": "adult"}, "encounter": {"date": TODAY.isoformat()},
                       "symptoms": {"status": "absent", "onset_date": (TODAY - timedelta(days=1)).isoformat()}},
                      "How should fever be assessed?")
    assert result["status"] == "rejected"


def test_private_api_requires_key_and_actor_claims(monkeypatch):
    monkeypatch.setenv("AFYA_CLINICIAN_API_KEY", "a-long-internal-test-secret")
    client = TestClient(app)
    payload = {"clinician_question": "What is Ebola?", "patient_summary": {
        "patient": {"age_group": "adult"}, "encounter": {"date": TODAY.isoformat()}}}
    assert client.post("/api/clinician/query", json=payload).status_code == 401
    headers = {"x-api-key": "a-long-internal-test-secret", "x-actor-claims-trust": "emr_access_token_authenticated",
               "x-user-id": "clinician-1", "x-facility": "facility-1", "x-user-role": "doctor",
               "x-purpose-of-use": "treatment"}
    result = client.post("/api/clinician/query", json=payload, headers=headers)
    assert result.status_code == 200
    assert result.json()["answer_status"] == "clinical_review_required"
    assert result.json()["patient_context_used"] is False


def test_readiness_fails_without_review_artifacts(tmp_path, monkeypatch):
    from apps.api.afya import core
    from evals.readiness import check
    monkeypatch.setattr(core, "DB", tmp_path / "data.sqlite3")
    monkeypatch.setattr(core, "PDF_DIR", tmp_path)
    result = check()
    assert result["ready"] is False
    assert result["failures"]
