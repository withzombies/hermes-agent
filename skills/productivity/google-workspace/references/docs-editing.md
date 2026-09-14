# Native Google Docs Editing

The wrapper supports `docs get`, `create`, `append`, `batch-update`, and
`insert-row`. Google Docs access is not read-only. Use the existing document ID
for edits; native tables must remain tables, not appended pipe-delimited text.

1. Run `$GAPI docs get DOC_ID --raw` to inspect the full document, including
   tables, text styles and links, tab IDs, structural indices, and `revisionId`.
2. For a table row, run `$GAPI docs insert-row DOC_ID --table-index INDEX
   --row-index ROW --below --tab TAB_ID --revision REVISION_ID`.
   ROW is zero-based; INDEX is the table element's `startIndex`.
3. Read `--raw` again after structural edits. Build a UTF-8 JSON file containing
   an array of native Docs API requests. Fill cells using `insertText` at each
   empty cell paragraph's `startIndex`. Order insertions from highest to lowest
   index so earlier insertions do not shift later targets. Include `tabId` in
   each location/range. Google indices count UTF-16 code units, not Python chars.
4. Run `$GAPI docs batch-update DOC_ID --requests-file /path/to/requests.json
   --revision REVISION_ID` using the revision from that latest read. A changed
   document rejects the write; read again and rebuild indices before retrying.
5. Read back and verify the requested cells, surrounding rows, and links.
   Each batch is atomic; row insertion and filling are separate writes. If filling
   fails, inspect the existing empty row and complete it rather than inserting another.

`batch-update` also supports replacing text, text styles, clickable links,
table formatting, and other native Docs operations. For example:

```json
[{"insertText":{"location":{"index":12,"tabId":"t.0"},"text":"Venue name"}}]
```

For hyperlinks use `updateTextStyle` with a range, `textStyle.link.url`, and
`fields: "link"`. Keep confirmed facts distinct from provisional planning ranges.

API reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request
