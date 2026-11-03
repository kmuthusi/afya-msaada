from apps.api.afya.retrieval.planner import coverage, plan, queries


def test_transmission_timing_requires_two_components():
    evidence_plan = plan("Can Ebola spread before symptoms?")
    assert evidence_plan.name == "transmission"
    assert [need.name for need in evidence_plan.needs] == ["route", "timing"]
    result = coverage(evidence_plan, [{"text": "Contact with blood and other body fluids."}])
    assert result["missing"] == ["timing"]
    assert any("symptom onset" in q for q in queries("Can Ebola spread before symptoms?", evidence_plan))
