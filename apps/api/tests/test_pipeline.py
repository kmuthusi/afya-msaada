from apps.api.afya.answering import pipeline


def test_unsupported_absence_claim_is_rejected(monkeypatch):
    replies = iter([
        {"ids": [1]},
        {"answer": "There is no direct evidence that shaking hands transmits Ebola.", "ids": [1]},
    ])
    monkeypatch.setattr(pipeline, "chat_json", lambda *args, **kwargs: next(replies))
    source = {"filename": "guide.pdf", "page": 2, "text": "Ebola spreads through contact with blood and body fluids."}
    assert pipeline.draft_and_verify("Can I get Ebola by shaking hands?", [source]) is None


def test_supported_answer_requires_relevance_check(monkeypatch):
    replies = iter([
        {"ids": [1]},
        {"answer": "Ebola spreads through contact with blood and body fluids.", "ids": [1]},
        {"supported": True, "relevant": False},
    ])
    monkeypatch.setattr(pipeline, "chat_json", lambda *args, **kwargs: next(replies))
    source = {"filename": "guide.pdf", "page": 2, "text": "Ebola spreads through contact with blood and body fluids."}
    assert pipeline.draft_and_verify("How deadly is Ebola?", [source]) is None
