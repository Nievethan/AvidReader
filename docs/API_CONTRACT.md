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

## Word Wall

### `POST /api/v1/books/{book_id}/words`

```json
{"word": "lugubrious", "meaning": "mournful", "quote": "a lugubrious sigh", "source_location": "page 4"}
```

Only `word` is required (1-200 chars); `meaning`, `quote`, `source_location`
are all optional free text. There is no AI behind this yet -- the caller
(frontend, or a future call to `/ai/chat` with `interaction_type: "explain"`)
supplies the meaning itself; the backend only persists it.

**201 Created:**

```json
{
  "id": "f6ac45b8-...",
  "book_id": "40fae399-...",
  "word": "lugubrious",
  "meaning": "mournful",
  "quote": "a lugubrious sigh",
  "source_location": "page 4",
  "created_at": "2026-11-12T01:30:49.419375"
}
```

### `GET /api/v1/books/{book_id}/words`

```json
{"items": [ { "...": "same shape as above" } ], "total": 1}
```

Ordered newest first.

### `DELETE /api/v1/books/{book_id}/words/{word_id}`

`204 No Content`, or `404` if the word doesn't exist for that book (a word
ID from a different book 404s too -- entries are scoped to their book).

---

## Character Map (relationships)

**Status (2026-11-12): implemented and wired to real Cloudflare extraction**,
with one deliberate design choice: it does **not** regenerate on every page
view. `GET` only ever reads a cache; a separate `POST .../generate` (the
"Update" button) does the real (costed) extraction and replaces the cache.
Live-verified against a real uploaded book (Harry Potter, pages 1-15):
real character nodes (Harry Potter, the Dursleys, Dumbledore, McGonagall,
Hagrid) and real grounded relationship edges, each with a verbatim quote
checked against the actual book text.

### `GET /api/v1/books/{book_id}/relationships`

Returns whatever's cached from the last `generate` call -- free, no model
call. `not_available` if nothing has been generated yet, or if the last
generation attempt found nothing groundable:

```json
{
  "book_id": "40fae399-...",
  "status": "not_available",
  "source": "none",
  "message": "Nothing generated yet -- tap Update to extract characters from what you've read so far.",
  "nodes": [],
  "edges": [],
  "generated_at": null,
  "boundary_label": null
}
```

### `POST /api/v1/books/{book_id}/relationships/generate`

The "Update" button. Sends everything the reader has read so far
(`RetrievalProvider.list_chunks`, spoiler-bounded by saved progress) in one
prompt, grounds the model's JSON against that real text (a character must
actually be named in the excerpts; every relationship's evidence must be an
exact quote found in them), and replaces the cache. Costs a real Cloudflare
call -- not triggered by `GET`, and not auto-triggered on page load.

```json
{
  "book_id": "40fae399-...",
  "status": "ready",
  "source": "extracted",
  "message": null,
  "nodes": [
    {"id": "char_harry_potter", "name": "Harry Potter", "role": "protagonist", "description": "a young wizard Traits: brave, resilient.", "first_seen_chunk_id": "40fae399-...:0"}
  ],
  "edges": [
    {"id": "rel_char_harry_potter_char_hagrid_ally", "source": "char_harry_potter", "target": "char_hagrid", "relationship": "ally", "label": "Hagrid brought him his letter", "evidence": "I've got him, sir."}
  ],
  "generated_at": "2026-11-12T02:14:52.454839",
  "boundary_label": "page 15"
}
```

`status` stays `not_available` (not an error) if: the book isn't ready yet,
nothing has been read, the model's response couldn't be parsed as JSON, or
every character/relationship it proposed failed grounding. `source` is
`"extracted"` for real results; mark any future seeded demo data
`"fixture"`.

`node` shape: `{id, name, role, description, first_seen_chunk_id}`. `edge`
shape: `{id, source, target, relationship, label, evidence}`. Relationship
name matching is fuzzy on purpose (handles the model saying "Dumbledore"
in `relationships` after saying "Albus Dumbledore" in `characters`), but a
name word shared by two different characters is treated as ambiguous and
the edge is dropped rather than guessed.

Both routes: `404 NOT_FOUND` if the book doesn't exist.

---

## Reading log and achievements

Both are computed from real data (reading progress updates, chat
messages, uploaded books) -- nothing here is a mock or fixture.

### `GET /api/v1/reading-log`

Global, not per-book (matches the dashboard-level reading log in the
original design). Every `PUT .../progress` call upserts one entry for
today's UTC date for that book; the same book/day combo updates in place
rather than duplicating.

```json
{
  "days": [
    {"date": "2026-11-12", "book_id": "40fae399-...", "book_title": "SplitPDF", "current_page": 5, "current_chapter": null}
  ],
  "current_streak": 1,
  "longest_streak": 1
}
```

`current_streak` counts consecutive calendar days up to today (or
yesterday, if nothing has been logged yet today -- so the streak isn't
shown as broken before the reader has had a chance to read).
`longest_streak` is the longest run ever, across all books.

### `GET /api/v1/achievements`

```json
{
  "achievements": [
    {"id": "first_upload", "label": "Shelved your first book", "description": "Upload a book to your library.", "unlocked": true},
    {"id": "first_question", "label": "Curious mind", "description": "Ask the AI your first question about a book.", "unlocked": false},
    {"id": "finished_a_book", "label": "The End", "description": "Finish reading a book.", "unlocked": false},
    {"id": "three_day_streak", "label": "Building a habit", "description": "Read on 3 days in a row.", "unlocked": false},
    {"id": "seven_day_streak", "label": "A week of reading", "description": "Read on 7 days in a row.", "unlocked": false},
    {"id": "library_of_five", "label": "Growing library", "description": "Upload 5 books.", "unlocked": false}
  ],
  "current_streak": 0,
  "longest_streak": 0
}
```

`unlocked` is computed live on every request from books/progress/reading-log/
messages -- there is no separate "unlocked achievements" table, so nothing
can get out of sync. This is a fixed starter list, not a final design;
discuss with the team before adding/removing achievement IDs, since the
frontend will key off them.

---

## Not implemented yet (documented, not silently dropped)

These are in the original proposal but intentionally **not** built in
this PR -- see `docs/BACKEND_CONTEXT.md` for the implemented/mocked/
planned table:

- `GET /api/v1/books/{book_id}/characters` (a separate per-character detail
  view, distinct from the relationships graph above)
- `POST /api/v1/visualizations`, `/api/v1/study/*`
- Image/portrait generation (no hook anywhere yet, not even a `not_available`
  route -- no AI model is connected for this)

Do not build a frontend screen against any of the above until they
actually exist in this contract.
