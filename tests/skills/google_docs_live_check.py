"""Opt-in live CLI check. Creates one temporary Doc and trashes it in finally."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    script = Path(sys.argv[1]).resolve()

    def call(*args, check=True):
        result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
        if not check:
            return result
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)

    def read(doc_id):
        return call("docs", "get", doc_id, "--raw")

    with tempfile.TemporaryDirectory(prefix="hermes-docs-check-") as directory:
        request_file = Path(directory) / "requests.json"

        def update(doc_id, doc, requests):
            request_file.write_text(json.dumps(requests), encoding="utf-8")
            return call("docs", "batch-update", doc_id, "--requests-file", str(request_file),
                        "--revision", doc["revisionId"])

        doc_id = call("docs", "create", "--title", "Hermes Docs deployment verification (temporary)")["documentId"]
        print(f"Created temporary verification Doc: {doc_id}", flush=True)
        try:
            doc = read(doc_id)
            tab = doc["tabs"][0]["tabProperties"]["tabId"]
            update(doc_id, doc, [{"insertTable": {"rows": 2, "columns": 2,
                                                  "location": {"index": 1, "tabId": tab}}}])
            doc = read(doc_id)
            table = next(el for el in doc["tabs"][0]["documentTab"]["body"]["content"] if "table" in el)
            call("docs", "insert-row", doc_id, "--table-index", str(table["startIndex"]),
                 "--row-index", "0", "--below", "--tab", tab, "--revision", doc["revisionId"])
            doc = read(doc_id)
            table = next(el for el in doc["tabs"][0]["documentTab"]["body"]["content"] if "table" in el)
            assert table["table"]["rows"] == 3
            cells = table["table"]["tableRows"][1]["tableCells"]
            requests = [{"insertText": {"location": {"index": cell["content"][0]["startIndex"], "tabId": tab}, "text": text}}
                        for cell, text in reversed(list(zip(cells, ["Verification venue", "Pending quote"])))]
            update(doc_id, doc, requests)
            assert "Verification venue" in call("docs", "get", doc_id)["body"]
            stale = call("docs", "batch-update", doc_id, "--requests-file", str(request_file),
                         "--revision", doc["revisionId"], check=False)
            assert stale.returncode != 0, "Stale revision was accepted"
            doc = read(doc_id)
            table = next(el for el in doc["tabs"][0]["documentTab"]["body"]["content"] if "table" in el)
            start = table["table"]["tableRows"][1]["tableCells"][0]["content"][0]["startIndex"]
            update(doc_id, doc, [{"updateTextStyle": {"range": {"startIndex": start, "endIndex": start + 18, "tabId": tab},
                                                    "textStyle": {"link": {"url": "https://example.com/"}}, "fields": "link"}}])
            assert "https://example.com/" in json.dumps(read(doc_id))
            print("PASS: native table creation, row insertion, cell writes, text reads, links, stale-revision rejection", flush=True)
        finally:
            result = call("drive", "delete", doc_id)
            assert result["status"] == "trashed"
            print("Temporary verification Doc moved to trash", flush=True)


if __name__ == "__main__":
    main()
