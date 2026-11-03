from apps.api.afya.sources.processor import chunks, reference_page


def test_reference_page_filter_and_sentence_chunks():
    assert reference_page("References\n1. An article")
    assert not reference_page("Clinical guidance\nThe recommendation is discussed here.")
    text = "Ebola disease is severe. " * 90
    parts = chunks(text, max_chars=300)
    assert len(parts) > 1
    assert all(len(part) <= 300 for part in parts)
