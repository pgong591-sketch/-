import pandas as pd

import app


def test_detail_query_table_freezes_header_and_first_identifier_column():
    html = app._detail_query_table_html(
        pd.DataFrame(
            [
                {"公司编码": "1010101", "期间": "202603", "金额": 1234.5},
                {"公司编码": "10204", "期间": "202603", "金额": -50.0},
            ]
        )
    )

    assert "detail-query-table-wrap" in html
    assert "overflow:auto" in html
    assert ".detail-query-table th{position:sticky;top:0;z-index:4" in html
    assert ".detail-query-table th:first-child{left:0;z-index:7" in html
    assert ".detail-query-table td:first-child{position:sticky;left:0;z-index:3" in html
    assert "1,234.50" in html
    assert "&lt;" not in html


def test_detail_query_large_result_uses_dataframe_without_full_html(monkeypatch):
    large_df = pd.DataFrame(
        {
            "公司编码": [f"C{i:04d}" for i in range(app.DETAIL_QUERY_HTML_ROW_LIMIT + 1)],
            "金额": list(range(app.DETAIL_QUERY_HTML_ROW_LIMIT + 1)),
        }
    )
    calls = {"warning": [], "download": [], "dataframe": [], "markdown": []}

    monkeypatch.setattr(app, "_detail_query_table_html", lambda df: (_ for _ in ()).throw(AssertionError("should not build full HTML")))
    monkeypatch.setattr(app.st, "warning", lambda message: calls["warning"].append(message))
    monkeypatch.setattr(app.st, "download_button", lambda *args, **kwargs: calls["download"].append((args, kwargs)))
    monkeypatch.setattr(app.st, "dataframe", lambda df, **kwargs: calls["dataframe"].append((df, kwargs)))
    monkeypatch.setattr(app.st, "markdown", lambda *args, **kwargs: calls["markdown"].append((args, kwargs)))

    app._render_detail_query_result(large_df, {}, "损益明细表", None, None)

    assert calls["warning"]
    assert calls["download"]
    assert len(calls["dataframe"]) == 1
    assert len(calls["dataframe"][0][0]) == app.DETAIL_QUERY_HTML_ROW_LIMIT + 1
    assert calls["markdown"] == []
