"""Structured Docs reads and revision-checked native edits for the local fork."""

from __future__ import annotations

import json
from pathlib import Path


def extract_body_text(body):
    parts = []
    for element in body.get("content", []):
        for run in element.get("paragraph", {}).get("elements", []):
            parts.append(run.get("textRun", {}).get("content", ""))
        for row in element.get("table", {}).get("tableRows", []):
            parts.append("\t".join(extract_body_text(cell).rstrip("\n")
                                   for cell in row.get("tableCells", [])) + "\n")
        if "tableOfContents" in element:
            parts.append(extract_body_text(element["tableOfContents"]))
    return "".join(parts)


def _read(api, doc_id):
    params = {"documentId": doc_id, "includeTabsContent": True}
    if api["_gws_binary"]():
        return api["_run_gws"](["docs", "documents", "get"], params=params)
    return api["build_service"]("docs", "v1").documents().get(**params).execute()


def _update(api, doc_id, requests, revision):
    if not isinstance(requests, list) or not requests or any(
        not isinstance(request, dict) or len(request) != 1 for request in requests
    ):
        raise ValueError("requests must be a nonempty array of single-operation objects")
    if not revision or not revision.strip():
        raise ValueError("Pass the revisionId from docs get --raw using --revision")
    body = {"requests": requests, "writeControl": {"requiredRevisionId": revision}}
    if api["_gws_binary"]():
        return api["_run_gws"](["docs", "documents", "batchUpdate"],
                               params={"documentId": doc_id}, body=body)
    return api["build_service"]("docs", "v1").documents().batchUpdate(
        documentId=doc_id, body=body).execute()


def register_commands(sub, api):
    """Extend the existing CLI without adding any model tool schema."""
    get_parser = sub.choices["get"]
    get_parser.add_argument("--raw", action="store_true",
                            help="Full document JSON: tabs, tables, styles, indices, revisionId")
    original_get = api["docs_get"]

    def get(args):
        if args.raw:
            print(json.dumps(_read(api, args.doc_id), ensure_ascii=False, indent=2))
        else:
            original_get(args)

    get_parser.set_defaults(func=get)

    def batch(args):
        try:
            requests = json.loads(Path(args.requests_file).read_text(encoding="utf-8"))
            result = _update(api, args.doc_id, requests, args.revision)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    parser = sub.add_parser("batch-update", help="Apply native Docs API requests atomically")
    parser.add_argument("doc_id")
    parser.add_argument("--requests-file", required=True, help="UTF-8 JSON array of Docs API requests")
    parser.add_argument("--revision", required=True, help="revisionId from docs get --raw")
    parser.set_defaults(func=batch)

    def insert_row(args):
        doc = _read(api, args.doc_id)
        if doc.get("revisionId") != args.revision:
            row_parser.error("Document changed; read it again before inserting a row")
        tab_id, body = api["_resolve_write_tab"](doc, args.tab)
        table = next((el["table"] for el in body.get("content", [])
                      if el.get("startIndex") == args.table_index and "table" in el), None)
        if table is None or not 0 <= args.row_index < table.get("rows", 0):
            row_parser.error("Table or row index does not exist in the selected tab")
        location = {"index": args.table_index}
        if tab_id:
            location["tabId"] = tab_id
        result = _update(api, args.doc_id, [{"insertTableRow": {
            "tableCellLocation": {"tableStartLocation": location,
                                  "rowIndex": args.row_index, "columnIndex": 0},
            "insertBelow": args.below,
        }}], args.revision)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    row_parser = sub.add_parser("insert-row", help="Insert an empty native table row; read back before filling cells")
    row_parser.add_argument("doc_id")
    row_parser.add_argument("--table-index", required=True, type=int)
    row_parser.add_argument("--row-index", required=True, type=int, help="Zero-based reference row")
    row_parser.add_argument("--below", action="store_true", help="Insert below reference row (default: above)")
    row_parser.add_argument("--tab", default=None)
    row_parser.add_argument("--revision", required=True)
    row_parser.set_defaults(func=insert_row)
