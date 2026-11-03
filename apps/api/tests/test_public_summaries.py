from apps.api.afya import core


def test_short_public_overviews_require_approved_source_passages(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB", tmp_path / "test.sqlite3")
    monkeypatch.setattr(core, "PDF_DIR", tmp_path)
    fixtures = (
        ("ipc-ebola-marburg-2026.pdf", 17,
         "Patients with suspected or confirmed Ebola disease (EBOD) or Marburg disease (MARD) should be isolated, preferably in a single room, and health workers should wear PPE.",
         "ebola case isolation guidance", "source_bound_isolation_overview"),
        ("diagnostic-testing-ebola-marburg-2026.pdf", 12,
         "Outcomes improve with early diagnosis, optimized supportive care and targeted therapeutics. Countermeasures are specific to each virus species.",
         "ebola treatment", "source_bound_treatment_overview"),
        ("who-bundibugyo-public-health-advice-camp-settings-2026.pdf", 7,
         "There is currently no licensed vaccine against BDBV. The approved Ebola vaccine currently works for Ebola virus disease, caused by a different virus species.",
         "ebola vaccine", "source_bound_vaccine_overview"),
    )
    with core.connect() as con:
        for filename, page, passage, _, _ in fixtures:
            pdf = tmp_path / filename
            pdf.write_bytes(filename.encode())
            sha = core.digest(pdf)
            con.execute("INSERT INTO sources(filename,sha256,tier,diseases,status) VALUES(?,?,?,?,?)",
                        (filename, sha, "public", '["Ebola"]', "approved"))
            con.execute("INSERT INTO passages(filename,sha256,page,text) VALUES(?,?,?,?)",
                        (filename, sha, page, passage))
    for filename, page, _, question, reason in fixtures:
        result = core.answer(question)
        assert result["status"] == "answered"
        assert result["reason"] == reason
        assert result["citations"][0]["filename"] == filename
        assert result["citations"][0]["page"] == page
    assert core.answer("Which Ebola vaccine should I get?")["reason"] == "current_vaccine_guidance_needed"
    assert core.answer("How should I isolate a patient with Ebola?")["reason"] == "personal_medical_advice"
    core.change_status(fixtures[2][0], "revoke", "Reviewer", "Superseded")
    assert core.answer("ebola vaccine")["status"] == "declined"
