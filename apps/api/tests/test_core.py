from apps.api.afya import core


def test_followup_asks_for_disease_when_ambiguous():
    result = core.answer("How does it spread?", [])
    assert result["status"] == "clarify"
    assert result["citations"] == []


def test_current_outbreak_declines_without_citation():
    result = core.answer("How many Ebola cases today?")
    assert result["reason"] == "current_information_unavailable"
    assert result["citations"] == []


def test_personal_exposure_declines():
    result = core.answer("I was exposed to Ebola; am I infected?")
    assert result["reason"] == "personal_medical_advice"


def test_screenshot_personal_and_broad_questions_are_not_unrelated_excerpts():
    assert core.answer("if I have ebola will I die?")["reason"] == "personal_medical_advice"
    assert core.answer("if I suspect I have ebola, what should I do?")["reason"] == "personal_medical_advice"
    assert core.answer("guidance for ebola case management")["reason"] == "broad_clinical_guidance"


def test_screenshot_overview_and_handshake_use_relevant_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB", tmp_path / "test.sqlite3")
    monkeypatch.setattr(core, "PDF_DIR", tmp_path)
    pdf = tmp_path / "guide.pdf"
    pdf.write_bytes(b"fixture")
    with core.connect() as con:
        con.execute("INSERT INTO sources(filename,sha256,tier,diseases,status) VALUES(?,?,?,?,?)",
                    (pdf.name, core.digest(pdf), "public", '["Ebola"]', "approved"))
        con.execute("INSERT INTO passages(filename,sha256,page,text) VALUES(?,?,?,?)",
                    (pdf.name, core.digest(pdf), 12, "Ebola virus disease (EVD) is a highly infectious, severe, and often fatal illness in humans. The virus spreads through contact with body secretions and fluids."))
        con.execute("INSERT INTO passages(filename,sha256,page,text) VALUES(?,?,?,?)",
                    (pdf.name, core.digest(pdf), 37, "Human-to-human transmission occurs via exposure to blood and other body fluids via direct or indirect contact."))
    overview = core.answer("tell me about ebola")
    assert overview["status"] == "answered"
    assert "Ebola virus disease" in overview["answer"]
    assert overview["citations"][0]["page"] == 12
    handshake = core.answer("can I get ebola by shaking hands?")
    assert handshake["status"] == "answered"
    assert "cannot determine" in handshake["answer"]
    assert "body fluids" in handshake["citations"][0]["excerpt"]


def test_procedural_question_declines_before_model():
    result = core.answer("Which intravenous fluid should I use for Ebola resuscitation?")
    assert result["reason"] == "professional_clinical_guidance"


def test_approved_source_search_and_revoke(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB", tmp_path / "test.sqlite3")
    with core.connect() as con:
        con.execute("INSERT INTO sources(filename,sha256,tier,diseases,status) VALUES(?,?,?,?,?)",
                    ("sample.pdf", "hash", "public", '["Ebola"]', "approved"))
        con.execute("INSERT INTO passages(filename,sha256,page,text) VALUES(?,?,?,?)",
                    ("sample.pdf", "hash", 2, "Ebola disease can spread through direct contact with infected body fluids."))
    assert core.search("How does Ebola spread through contact?")
    core.change_status("sample.pdf", "revoke", "Test reviewer", "Superseded")
    assert not core.search("How does Ebola spread through contact?")


def test_changed_pdf_is_auto_revoked(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DB", tmp_path / "test.sqlite3")
    monkeypatch.setattr(core, "PDF_DIR", tmp_path)
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"first version")
    with core.connect() as con:
        con.execute("INSERT INTO sources(filename,sha256,tier,diseases,status) VALUES(?,?,?,?,?)",
                    (pdf.name, core.digest(pdf), "public", '["Ebola"]', "approved"))
    pdf.write_bytes(b"second version")
    assert core.revoke_stale_sources() == [pdf.name]
    assert core.sources()[0]["status"] == "revoked"
