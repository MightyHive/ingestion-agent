"""Unit tests for ``ingestion.nodes.format_response``."""

from __future__ import annotations

from ingestion.nodes.format_response import PREVIEW_ROWS, format_response


def _manifest(response_subkey: str | None = None) -> dict:
    m = {
        "id": "test_mock_connector",
        "platform": "test",
        "connector": "mock",
        "version": "0.1.0",
    }
    if response_subkey:
        m["metadata"] = {"response_subkey": response_subkey}
    return m


def test_format_list_records() -> None:
    resp = {
        "status": "ok",
        "code": 200,
        "records": [{"id": "a"}, {"id": "b"}],
        "meta": {"x": 1},
        "errors": [],
        "diagnostics": {"backend": "local"},
    }
    lol = format_response(_manifest(), ["id"], "bronze.t", "DDL;\n", resp, "dev")
    assert lol.status == "OK"
    body = lol.data["formatted_response"]
    assert body["row_count"] == 2
    assert body["rows_preview"] == [{"id": "a"}, {"id": "b"}]
    assert body["target_table"] == "bronze.t"
    assert body["ddl"] == "DDL;\n"


def test_format_dict_records_with_subkey() -> None:
    resp = {
        "status": "ok",
        "code": 200,
        "records": {"ads": [{"id": "1"}], "campaigns": [{"id": "X"}]},
        "meta": {},
        "errors": [],
    }
    lol = format_response(
        _manifest(response_subkey="ads"), ["id"], "bronze.t", "", resp, "dev"
    )
    assert lol.status == "OK"
    assert lol.data["formatted_response"]["row_count"] == 1


def test_format_dict_records_without_subkey_warns() -> None:
    resp = {
        "status": "ok",
        "code": 200,
        "records": {"ads": [{"id": "1"}], "campaigns": [{"id": "X"}]},
        "meta": {},
        "errors": [],
    }
    lol = format_response(_manifest(), ["id"], "bronze.t", "", resp, "dev")
    assert lol.status == "WARN"
    assert lol.data["formatted_response"]["row_count"] == 0


def test_format_preview_capped() -> None:
    rows = [{"id": str(i)} for i in range(PREVIEW_ROWS + 10)]
    resp = {"status": "ok", "code": 200, "records": rows, "meta": {}, "errors": []}
    lol = format_response(_manifest(), ["id"], "bronze.t", "", resp, "dev")
    assert lol.data["formatted_response"]["row_count"] == PREVIEW_ROWS + 10
    assert len(lol.data["formatted_response"]["rows_preview"]) == PREVIEW_ROWS
