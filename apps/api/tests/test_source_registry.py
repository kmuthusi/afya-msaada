import json

import pytest

from apps.api.afya import core
from apps.api.afya.sources.registry import register


def test_register_stages_metadata_without_approval(tmp_path, monkeypatch):
    target = tmp_path / "manifest.json"
    target.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(core, "MANIFEST", target)
    created = register("new-guidance.pdf", "public", ["Ebola"], "https://example.org/guidance")
    assert created["legacy_approval"] is None
    assert json.loads(target.read_text(encoding="utf-8"))[0]["filename"] == "new-guidance.pdf"
    with pytest.raises(ValueError, match="already"):
        register("new-guidance.pdf", "public", ["Ebola"])
    with pytest.raises(ValueError, match="basename"):
        register("../escape.pdf", "public", ["Ebola"])
