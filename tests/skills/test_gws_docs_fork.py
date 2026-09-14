"""Contracts for native Google Docs editing on both supported transports."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


PATH = Path(__file__).resolve().parents[2] / "skills/productivity/google-workspace/scripts/_gws_docs.py"
spec = importlib.util.spec_from_file_location("gws_docs_fork", PATH)
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def paragraph(text):
    return {"paragraph": {"elements": [{"textRun": {"content": text}}]}}


def test_reader_includes_table_cells_and_nested_tables():
    body = {"content": [paragraph("Title\n"), {"table": {"tableRows": [
        {"tableCells": [{"content": [paragraph("Venue\n")]},
                        {"content": [paragraph("Price\n")]}]},
    ]}}, paragraph("After\n")]}
    assert docs.extract_body_text(body) == "Title\nVenue\tPrice\nAfter\n"
    assert docs.extract_body_text({"content": [{"tableOfContents": body}]}) == docs.extract_body_text(body)


@pytest.mark.parametrize("gws", [True, False])
def test_revision_guard_reaches_both_transports(gws):
    run = MagicMock(return_value={"documentId": "doc"})
    service = MagicMock()
    service.documents.return_value.batchUpdate.return_value.execute.return_value = {"documentId": "doc"}
    api = {"_gws_binary": lambda: gws, "_run_gws": run, "build_service": lambda *a: service}
    requests = [{"insertText": {"location": {"index": 7, "tabId": "tab"}, "text": "Venue"}}]
    assert docs._update(api, "doc", requests, "revision") == {"documentId": "doc"}
    body = {"requests": requests, "writeControl": {"requiredRevisionId": "revision"}}
    if gws:
        run.assert_called_once_with(["docs", "documents", "batchUpdate"], params={"documentId": "doc"}, body=body)
    else:
        service.documents.return_value.batchUpdate.assert_called_once_with(documentId="doc", body=body)


@pytest.mark.parametrize("requests,revision", [([], "r"), ({}, "r"), ([{}], "r"), ([{"insertText": {}}], "")])
def test_invalid_updates_never_reach_transport(requests, revision):
    with pytest.raises(ValueError):
        docs._update({}, "doc", requests, revision)
