# AvidReader Backend API Contract (v1)

**Status:** Describes endpoints that exist and are tested in this repo
right now, as of this PR. Base path for versioned routes: `/api/v1`.
`/health` and `/ready` are unversioned, at the root.

This is a provisional, team-reviewable contract, not a frozen spec.
Discuss breaking changes with the team before merging them.

**If you change an endpoint's request/response shape, status codes,
or add/remove a route -- update this file in the same PR.** Treat it
as part of the diff, not a follow-up task. This is what everyone
(including your own Claude/AI session, which won't otherwise know the
contract changed) checks first before touching the API.

## Conventions

- IDs are UUID strings.
- Timestamps are UTC ISO-8601.
- List endpoints return `{"items": [...], "total": N}`.
- Errors return `{"error": {"code": "SOME_CODE", "message": "..."}}`
  with an appropriate HTTP status (404, 409, 413, 415, 422, 503, 500).
- All of this is also live and interactive at `/docs` (Swagger UI) and
  `/openapi.json` when the server is running.

---

## Meta

### `GET /health`

Process-alive check only. Never claims a database or AI dependency is
connected.

```json
{"status": "ok"}
```

### `GET /ready`

Reports real dependency status. `database` is checked with a query and
`vector_store` with a real Qdrant call (`mode`: `server` when `QDRANT_URL`
is set, `local` for embedded Qdrant on disk, `memory` in tests). Neo4j is
only reported as configured or not; no client is wired in yet. Overall
`status` is `degraded` if the database or Qdrant check fails.

```json
{
  "status": "ready",
  "database": {"status": "ok"},
  "vector_store": {"configured": true, "mode": "server", "status": "ok"},
  "optional_dependencies": {
    "neo4j": {"configured": false, "status": "not_checked", "note": "..."}
  }
}
```

On failure: `"vector_store": {"configured": true, "mode": "server", "status": "error", "message": "ConnectError: ..."}`.

---

## Books

### `POST /api/v1/books`

`multipart/form-data`: `file` (required, PDF or EPUB), `title`
(optional), `author` (optional).

File validation is by actual content, not extension: PDF must start
with `%PDF-`; EPUB must be a zip whose `mimetype` entry is
`application/epub+zip`. Anything else is rejected with `415`.

**201 Created** (returns immediately; indexing runs in the background):

```json
{
  "id": "40fae399-b025-4bc3-a17f-f51ba31fc493",
  "title": "Smoke Test Book",
  "author": "Capstone Team",
  "filename": "smoke_sample.pdf",
  "file_type": "pdf",
  "file_size_bytes": 14,
  "processing_status": "processing",
  "processing_message": null,
  "total_pages": null,
  "chunk_count": null,
  "created_at": "2026-10-30T15:19:59.521513",
  "updated_at": "2026-10-30T15:19:59.521513"
}
```

`processing_status` is always truthful:

| Status | Meaning |
|---|---|
| `processing` | Being indexed (extract, clean, chunk, embed, store) |
| `ready` | Indexed; `total_pages` (PDF) and `chunk_count` are set |
| `unsupported` | No extractable text, e.g. a scanned PDF (`processing_message` says why) |
| `failed` | Corrupt file, embedding or Qdrant error, or interrupted twice by restarts |
| `uploaded` | Legacy value from before ingestion existed |

Poll `GET /api/v1/books/{book_id}/ingestion` (or `GET /api/v1/books/{id}`)
until the status leaves `processing`. `BookResponse` gained `chunk_count`.

Errors: `415 UNSUPPORTED_FILE_TYPE`, `413 FILE_TOO_LARGE`.

### `GET /api/v1/books`

```json
{"items": [ { "...": "BookResponse" } ], "total": 1}
```

### `GET /api/v1/books/{book_id}`

Returns a single `BookResponse`, or `404 NOT_FOUND`.

### `DELETE /api/v1/books/{book_id}`

Deletes the DB row, the stored file, the book's vectors in Qdrant and its
saved text. If Qdrant is unreachable the book is still deleted (a warning is
logged). `204 No Content`, or `404`.

### `GET /api/v1/books/{book_id}/ingestion`

```json
{
  "book_id": "40fae399-...",
  "status": "ready",
  "message": null,
  "total_pages": 250,
  "chunk_count": 312,
  "attempts": 1,
  "updated_at": "2026-11-11T18:02:11.204512"
}
```

`attempts` counts ingestion starts (a restart mid-indexing retries once).
`404` if the book doesn't exist.

### `GET /api/v1/books/{book_id}/content`

Query: `page` (PDF, 1-based) or `chapter` (EPUB, 1-based); default is the
first. A PDF given only `chapter` reads it as a page number, and vice versa.

**Ready:**

```json
{
  "book_id": "40fae399-...",
  "status": "ready",
  "content": "Mr. and Mrs. Dursley, of number four, Privet Drive, ...",
  "reason": null,
  "unit": "page",
  "index": 1,
  "total": 250,
  "title": null
}
```

Text is cleaned (running headers, page numbers and line-break hyphens
removed); paragraphs are separated by blank lines. `title` is the chapter
title when the PDF outline or EPUB provides one.

**Not ready:** `status` is `processing` (still indexing) or
`not_available` (failed/unsupported, or saved text missing), with `reason`
and `content: null`.

Errors: `404` if the book doesn't exist or the page/chapter is out of range
(`"Page 999 is out of range (1-250)."`); `422` for `page`/`chapter` < 1.

---

## Reading progress

### `GET /api/v1/books/{book_id}/progress`

Before any update, all fields except `book_id` are `null`:

```json
{"book_id": "...", "current_page": null, "current_chapter": null, "location": null, "percent_complete": null, "updated_at": null}
```

### `PUT /api/v1/books/{book_id}/progress`

Request (all fields optional, partial updates allowed):

```json
{"current_page": 112, "current_chapter": 7, "location": null, "percent_complete": 35.0}
```

`current_page`/`current_chapter` must be `>= 0`; `percent_complete`
must be in `[0, 100]` -- violations return `422`. `location` is a free
text field reserved for an EPUB-specific anchor/CFI once Umer defines
one; no EPUB page numbers are fabricated.

Response is the resulting `ProgressResponse` (same shape as GET).

---

## AI chat (grounded answers)

### `POST /api/v1/ai/chat`

```json
{
  "book_id": "40fae399-...",
  "conversation_id": null,
  "question": "Why is the protagonist conflicted?",
  "mode": "research",
  "interaction_type": "question",
  "reading_position": {"current_page": 42, "current_chapter": 3, "location": null},
  "selected_passage": null,
  "explanation_level": "standard"
}
```

- `mode`: `study` | `research` | `creative`
- `interaction_type`: `question` | `explain` | `what_if` | `story_continues`
- `explanation_level`: `simple` | `standard` | `advanced`
- `reading_position`: the spoiler boundary. PDFs use `current_page`,
  EPUBs use `current_chapter`. If missing or empty, the saved reading
  progress is used; if there is none, the whole book is searched.
- `selected_passage`: the text being explained (`explain`).

**200 OK:**

```json
{
  "conversation_id": "e1899414-...",
  "message_id": "b3720357-...",
  "book_id": "40fae399-...",
  "answer": "Mr. Dursley saw a cat reading a map on the corner of the street [S1].",
  "answer_type": "grounded",
  "provider_status": "ok",
  "is_hypothetical": false,
  "citations": [
    {
      "marker": "S1",
      "chunk_id": "40fae399-...:2",
      "page_start": 3,
      "page_end": 3,
      "page": 3,
      "chapter": null,
      "source_location": "page 3",
      "snippet": "\"Little tyke,\" chortled Mr. Dursley as he left the house. ...",
      "score": 0.8013
    }
  ],
  "spoiler_scope": {"restricted_to_progress": true, "reason": "Limited to page 42 (your current position)."},
  "created_at": "2026-11-11T18:05:41.613607"
}
```

**Citation shape** (agreed superset): `marker` matches the `[S#]` in the
answer text; `page_start`/`page_end` are `null` for EPUBs (use `chapter`);
`page` equals `page_start` and exists so the current frontend chip
(`'p. ${c['page']}'`) keeps working; `snippet` is at most ~240 characters.

**`answer_type` / `provider_status`:**

| answer_type | provider_status | When |
|---|---|---|
| `grounded` | `ok` (or `fake` offline) | `question` / `explain` answered with at least one valid citation |
| `hypothetical` | `ok` / `fake` | `what_if`, `story_continues` (`is_hypothetical: true`) |
| `refusal` | `no_evidence` | Nothing relevant up to the reader's position, or the model found no answer. Text: "I couldn't find this in the part of the book you've read so far." |
| `unavailable` | `book_not_ready` | Book is still processing, failed or unsupported |
| `unavailable` | `provider_error` | The chat model timed out or errored |

How each interaction gets its context: `question`/`what_if` search the
book; `explain` searches with the selected passage; `story_continues` uses
the last few passages before the reader's position. Answers are checked
after generation: unknown `[S#]` markers are removed, quotations not found
in the excerpts lose their quote marks, copied sentences are removed from
story continuations, and a factual answer without a valid citation becomes a
refusal.

`spoiler_scope.restricted_to_progress` is `true` whenever a boundary was
applied, with the unit, value and source in `reason`.

Errors: `404 NOT_FOUND` if `book_id` doesn't exist, or if
`conversation_id` is given but doesn't belong to that book. Model failures
are not HTTP errors; they return `answer_type: "unavailable"`.

### `GET /api/v1/ai/conversations/{conversation_id}`

```json
{
  "id": "e1899414-...",
  "book_id": "40fae399-...",
  "created_at": "...",
  "messages": [
    {"id": "...", "role": "user", "content": "...", "answer_type": null, "is_hypothetical": false, "citations": [], "created_at": "..."},
    {"id": "...", "role": "assistant", "content": "...", "answer_type": "grounded", "is_hypothetical": false, "citations": [{"marker": "S1", "...": "Citation"}], "created_at": "..."}
  ]
}
```

`404 NOT_FOUND` if the conversation doesn't exist.

---

## Not implemented yet (documented, not silently dropped)

These are in the original proposal but intentionally **not** built in
this PR -- see `docs/BACKEND_CONTEXT.md` for the implemented/mocked/
planned table:

- `GET/POST /api/v1/books/{book_id}/words` (Word Wall)
- `GET /api/v1/books/{book_id}/characters`, `GET /api/v1/books/{book_id}/relationships`
- `GET /api/v1/books/{book_id}/activity`, `POST /api/v1/books/{book_id}/sessions`
- `GET /api/v1/achievements`
- `POST /api/v1/visualizations`, `/api/v1/study/*`

Do not build a frontend screen against any of the above until they
actually exist in this contract.
