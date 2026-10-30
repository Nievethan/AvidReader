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

Reports real dependency status. `database` is actually checked with a
query. `qdrant`/`neo4j` report whether they're *configured*, not
whether they're connected -- no client for either is wired in yet.

```json
{
  "status": "ready",
  "database": {"status": "ok"},
  "optional_dependencies": {
    "qdrant": {"configured": false, "status": "not_checked", "note": "..."},
    "neo4j": {"configured": false, "status": "not_checked", "note": "..."}
  }
}
```

---

## Books

### `POST /api/v1/books`

`multipart/form-data`: `file` (required, PDF or EPUB), `title`
(optional), `author` (optional).

File validation is by actual content, not extension: PDF must start
with `%PDF-`; EPUB must be a zip whose `mimetype` entry is
`application/epub+zip`. Anything else is rejected with `415`.

**201 Created:**

```json
{
  "id": "40fae399-b025-4bc3-a17f-f51ba31fc493",
  "title": "Smoke Test Book",
  "author": "Capstone Team",
  "filename": "smoke_sample.pdf",
  "file_type": "pdf",
  "file_size_bytes": 14,
  "processing_status": "uploaded",
  "processing_message": null,
  "total_pages": null,
  "created_at": "2026-10-30T15:19:59.521513",
  "updated_at": "2026-10-30T15:19:59.521513"
}
```

`processing_status` is always truthful: `uploaded` right now, because
no real parser is connected. It will never say `ready` until Umer's
ingestion actually runs. `total_pages` stays `null` until known for
real.

Errors: `415 UNSUPPORTED_FILE_TYPE`, `413 FILE_TOO_LARGE`.

### `GET /api/v1/books`

```json
{"items": [ { "...": "BookResponse" } ], "total": 1}
```

### `GET /api/v1/books/{book_id}`

Returns a single `BookResponse`, or `404 NOT_FOUND`.

### `DELETE /api/v1/books/{book_id}`

Deletes the DB row and the stored file. `204 No Content`, or `404`.

### `GET /api/v1/books/{book_id}/content`

Honest placeholder until Umer's parser exists:

```json
{
  "book_id": "40fae399-...",
  "status": "not_available",
  "content": null,
  "reason": "No ingestion/parsing pipeline is connected yet (Umer's work)."
}
```

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

## AI chat (mock provider)

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

**200 OK:**

```json
{
  "conversation_id": "e1899414-...",
  "message_id": "b3720357-...",
  "book_id": "40fae399-...",
  "answer": "[MOCK RESPONSE] Real AI/RAG is not connected yet. ...",
  "answer_type": "mock",
  "provider_status": "mock",
  "is_hypothetical": false,
  "citations": [],
  "spoiler_scope": {
    "restricted_to_progress": false,
    "reason": "RAG retrieval provider is not connected yet; no spoiler boundary is enforced."
  },
  "created_at": "2026-10-30T15:19:59.613607"
}
```

Rules enforced by the mock provider (`app/integrations/mock_ai.py`):
`citations` is always `[]` (no retrieval happened, so no real source
exists); `interaction_type` in `{what_if, story_continues}` always
sets `is_hypothetical: true` and `answer_type: "hypothetical"`; the
answer text is always prefixed `[MOCK RESPONSE]`.

Errors: `404 NOT_FOUND` if `book_id` doesn't exist, or if
`conversation_id` is given but doesn't belong to that book.

### `GET /api/v1/ai/conversations/{conversation_id}`

```json
{
  "id": "e1899414-...",
  "book_id": "40fae399-...",
  "created_at": "...",
  "messages": [
    {"id": "...", "role": "user", "content": "...", "answer_type": null, "is_hypothetical": false, "citations": [], "created_at": "..."},
    {"id": "...", "role": "assistant", "content": "...", "answer_type": "mock", "is_hypothetical": false, "citations": [], "created_at": "..."}
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
- `GET /api/v1/books/{book_id}/ingestion`
- `POST /api/v1/visualizations`, `/api/v1/study/*`

Do not build a frontend screen against any of the above until they
actually exist in this contract.
