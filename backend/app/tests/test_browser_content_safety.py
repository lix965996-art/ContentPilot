from app.publishers.browser_session import plain_text_to_html


def test_plain_text_to_html_escapes_markup_and_skips_blank_lines() -> None:
    rendered = plain_text_to_html('<script>alert("x")</script>\n\n正常 & 文本 <b>加粗</b>')

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&amp;" in rendered
    assert "&lt;b&gt;" in rendered
    assert rendered.count("<p>") == 2
    assert rendered.startswith("<p>")
    assert rendered.endswith("</p>")
