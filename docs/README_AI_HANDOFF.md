# AvidReader AI JSON prototype — team handoff

## What exists

`backend/scripts/test_avidreader_features_v3.py` is an **independent prototype**, not a connected FastAPI AI provider. It calls Cloudflare Qwen, prompts for six text features, validates basic response structure, and saves JSON under `backend/outputs/ai_tests/`.

Run from `backend/`:

```powershell
python scripts/test_avidreader_features_v3.py
```

Prerequisites: existing backend Python dependencies (`httpx`, `python-dotenv`) and your private `backend/.env` file containing `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. Never commit `.env` or real API credentials.

## What is not complete

- The script uses a **hardcoded Chapter 1 fictional passage**, not PDFs/EPUBs or saved reading progress.
- Character/map, environment, and Word Wall are **structured JSON**, not Flutter UI.
- The 'spoiler guard' test is fixture-specific; actual spoiler safety requires server-authoritative progress and filtered retrieval.
- The script does **not** generate image bytes. Actual illustration generation requires a separate image model/endpoint.
- Character IDs use simple name normalization. Real novels need per-book alias resolution (e.g., nicknames and titles).
- AI traits and descriptions are **not independently fact-checked**. Evidence quotes are checked for character-map edges and environment entries, but may still be semantically inaccurate. This is prototype-level validation.

## JSON contract

Each successful response has `schema_version`, `book_id`, `mode`, `status`, `reading_boundary`, `is_hypothetical`, `data`, `citations`, `error`, and `prototype_fixture_only`.

`character_map.data.nodes` is a list of `{id, name, role, traits, description, first_seen_chunk_id}`; `character_map.data.edges` is a list of `{id, source, target, relationship, label, evidence, evidence_chunk_ids}`. **Frontend draws the graph; AI never returns graph images or coordinates.**

Other `data` types:
- `what_if`: `scenario`, `title`, `story`, `characters_involved`, `based_on_chunk_ids`, `is_fictional`
- `story_continues`: `title`, `story`, `characters_involved`, `starting_chunk_id`, `is_fictional`
- `word_wall`: `entries[]` with word/meaning/explanation/quote/chunk ID
- `environment`: `locations[]` with name/description/atmosphere/prompt/evidence/chunk IDs
- `spoiler_guard`: `answer`, `is_known`, `source_chunk_ids`

Do **not** treat these experimental response formats as finalized shared API contracts without Abinav's review.

## Ownership / requests

- **Gitae (AI):** Cloudflare adapter, prompt hierarchy, normalizers, Character Map extraction and image-generation adapter. Move tested logic from `scripts/` into `app/integrations/` once contracts are approved.
- **Abinav (backend):** agree on typed request/response schemas, connect AI provider to existing FastAPI dependency injection/routing, fetch verified saved reading boundary, and safely serve generated images.
- **Umer (RAG):** implement parsing, canonical reading positions, and progress-filtered `RetrievedPassage` content; the full Character Map needs all read-so-far passages, not only a few similarity hits.
- **Nievethan (Flutter):** render each feature's JSON; build Character Map using node IDs and edge source/target IDs; do not call Cloudflare directly from Flutter.
- **Arno (QA/integration):** add mocked Cloudflare tests, invalid-JSON, timeout, 429, empty-response, and spoiler-boundary cases. CI must not require an API key.

## GitHub guidance

1. Commit `backend/scripts/test_avidreader_features_v3.py` and this README (suggest `docs/AI_HANDOFF.md` in repo).
2. **Do not commit** `backend/.env`, credentials, or generated `backend/outputs/`.
3. Use a feature branch such as `feature/ai-json-prototype` and open a PR for Abinav/Arno to review.
4. Integration will be a **follow-up PR** implementing provider interfaces from `backend/app/integrations/interfaces.py` and updating `docs/API_CONTRACT.md` and `docs/BACKEND_CONTEXT.md` with the team.
