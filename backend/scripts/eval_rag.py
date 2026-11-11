"""End-to-end evaluation of the RAG pipeline (roadmap Step 9).

Runs the real FastAPI app in-process against a temporary database and an
in-memory Qdrant, using whatever embedding / chat backends backend/.env
configures (Cloudflare when credentials are set):

    upload -> background ingestion -> reader text -> retrieval -> chat

and scores the answers against a labelled question set.

    # default: the 99-page SplitPDF.pdf and its question set (cheapest)
    python scripts/eval_rag.py

    # the full 250-page book (about 2.5x the embedding cost)
    python scripts/eval_rag.py "../Harry Potter, Book 1; The Sorcerer's Stone.pdf" \
        --dataset tests/eval/harry_potter_1.json

    # benchmark several chat models on the same questions
    python scripts/eval_rag.py --models @cf/meta/llama-3.3-70b-instruct-fp8-fast,@cf/qwen/qwen3-30b-a3b-fp8

Metrics
* ingestion pages/min                         (ER-05, target >= 50)
* retrieval hit@k: a gold page in the top-k   (ER-04, target >= 95%)
* answer accuracy: expected keyword present and a citation on a gold page
* refusal rate on questions the book can't answer
* spoiler safety: no citation past the reader's page, no forbidden words
* citation validity: grounded answers carry >= 1 citation
* chat latency p50 / p95                      (ER-02, target p95 < 2.5 s)

Faithfulness is measured with automatic checks (citations, verified quotes),
not a judge model; see the README.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent
DEFAULT_DATASET = BACKEND / "tests" / "eval" / "harry_potter_1_first99.json"
PAGE_TOLERANCE = 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "book",
        nargs="?",
        default=None,
        help="PDF/EPUB the dataset was written for (default: the dataset's default_book, relative to the repo root)",
    )
    p.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p.add_argument("--models", default="", help="comma-separated chat model ids to compare (default: configured one)")
    p.add_argument("--only", default="", help="comma-separated question types to run, e.g. answerable,spoiler")
    p.add_argument("--limit", type=int, default=0, help="max questions per type (0 = all)")
    p.add_argument("--ids", default="", help="comma-separated question ids to run, e.g. q05,q11")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--report", default="", help="write the full JSON report here")
    p.add_argument("--show-answers", action="store_true")
    return p.parse_args()


def isolate_environment(workdir: Path) -> None:
    """Temporary DB / uploads / text and in-memory Qdrant, so the evaluation
    never touches the developer's real data. Must run before importing app."""
    os.environ.update(
        DATABASE_URL=f"sqlite:///{(workdir / 'eval.db').as_posix()}",
        UPLOADS_DIR=str(workdir / "uploads"),
        EXTRACTED_DIR=str(workdir / "extracted"),
        QDRANT_URL="",
        QDRANT_LOCAL_PATH=":memory:",
        APP_ENV="eval",
    )
    sys.path.insert(0, str(BACKEND))


def overlaps(citation: dict, gold: list[int]) -> bool:
    start, end = citation.get("page_start"), citation.get("page_end")
    if start is None:
        return False
    return any(start - PAGE_TOLERANCE <= g <= (end or start) + PAGE_TOLERANCE for g in gold)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def select_questions(dataset: dict, only: str, limit: int, ids: str = "") -> list[dict]:
    wanted = {t.strip() for t in only.split(",") if t.strip()}
    wanted_ids = {i.strip() for i in ids.split(",") if i.strip()}
    picked, per_type = [], {}
    for q in dataset["questions"]:
        if (wanted and q["type"] not in wanted) or (wanted_ids and q["id"] not in wanted_ids):
            continue
        per_type[q["type"]] = per_type.get(q["type"], 0) + 1
        if limit and per_type[q["type"]] > limit:
            continue
        picked.append(q)
    return picked


def score(q: dict, body: dict) -> dict:
    answer = body["answer"].lower()
    citations = body["citations"]
    result = {"answer_type": body["answer_type"], "provider_status": body["provider_status"]}
    if q["type"] == "answerable":
        keyword = any(k.lower() in answer for k in q["keywords"])
        cited_gold = any(overlaps(c, q["gold_pages"]) for c in citations)
        result.update(correct=keyword and cited_gold, keyword=keyword, cited_gold=cited_gold)
    elif q["type"] == "unanswerable":
        result.update(correct=body["answer_type"] == "refusal")
    elif q["type"] == "spoiler":
        limit = q["current_page"]
        leak_cite = any((c.get("page_end") or 0) > limit for c in citations)
        leak_word = any(w.lower() in answer for w in q["forbidden"])
        result.update(correct=not leak_cite and not leak_word, leaked_citation=leak_cite, leaked_word=leak_word)
    else:  # hypothetical
        limit = q.get("current_page")
        within = all((c.get("page_end") or 0) <= limit for c in citations) if limit else True
        result.update(correct=body["is_hypothetical"] and within, labelled=body["is_hypothetical"], within=within)
    return result


def main() -> int:
    args = parse_args()
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if args.book:
        book = Path(args.book).expanduser().resolve()
    elif dataset.get("default_book"):
        book = REPO_ROOT / dataset["default_book"]
    else:
        sys.exit("Pass the book path (this dataset has no default_book).")
    if not book.is_file():
        sys.exit(f"Book not found: {book}")
    questions = select_questions(dataset, args.only, args.limit, args.ids)

    workdir = Path(tempfile.mkdtemp(prefix="avidreader-eval-"))
    isolate_environment(workdir)

    from fastapi.testclient import TestClient

    from app.api import deps
    from app.core.config import get_settings
    from app.integrations.interfaces import ReadingBoundary
    from app.main import create_app
    from app.rag.llm import CloudflareChatModel

    settings = get_settings()
    report: dict = {"book": book.name, "dataset": Path(args.dataset).name}

    with TestClient(create_app()) as client:
        embedder = deps.get_embedding_provider()
        answerer = deps.get_answer_provider()
        print(f"Embedder: {type(embedder).__name__} {embedder.model} | chat: {answerer.model.name} ({answerer.model.status})")

        # ---- 1. upload + ingestion (TestClient runs the background job before returning)
        started = time.perf_counter()
        response = client.post("/api/v1/books", files={"file": (book.name, book.read_bytes(), "application/pdf")})
        response.raise_for_status()
        book_id = response.json()["id"]
        status = client.get(f"/api/v1/books/{book_id}/ingestion").json()
        ingest_seconds = time.perf_counter() - started
        pages = status["total_pages"] or 0
        report["ingestion"] = {
            **status,
            "seconds": round(ingest_seconds, 2),
            "pages_per_minute": round(pages / ingest_seconds * 60) if ingest_seconds and pages else None,
        }
        print(f"Ingestion: {status['status']} | {pages} pages, {status['chunk_count']} chunks in "
              f"{ingest_seconds:.1f}s -> {report['ingestion']['pages_per_minute']} pages/min")
        if status["status"] != "ready":
            print(f"Stopping: ingestion ended as {status['status']}: {status['message']}")
            return 1

        # ---- 2. reader text
        content = client.get(f"/api/v1/books/{book_id}/content", params={"page": 1}).json()
        text = content["content"] or ""
        report["content_check"] = {"status": content["status"], "total": content["total"], "page_1_chars": len(text)}
        print(f"Reader text: page 1/{content['total']} {content['status']}, {len(text)} chars: {text[:70]!r}")

        # ---- 3. retrieval hit@k (independent of the chat model)
        retrieval = deps.get_retrieval_provider()
        hits = []
        for q in (q for q in questions if q["type"] == "answerable"):
            passages = client.portal.call(
                retrieval.retrieve, book_id, q["question"], ReadingBoundary(book_id=book_id), args.top_k
            )
            hit = any(
                p.page_start is not None
                and any(p.page_start - PAGE_TOLERANCE <= g <= p.page_end + PAGE_TOLERANCE for g in q["gold_pages"])
                for p in passages
            )
            hits.append(hit)
            if args.show_answers:
                print(f"  retrieved {q['id']}: {[(p.source_location, round(p.relevance_score or 0, 3)) for p in passages]}")
            if not hit:
                print(f"  retrieval miss {q['id']}: top pages {[p.source_location for p in passages]}")
        report["retrieval"] = {"k": args.top_k, "questions": len(hits),
                               "hit_rate": round(sum(hits) / len(hits), 3) if hits else None}
        print(f"Retrieval hit@{args.top_k}: {sum(hits)}/{len(hits)}")

        # ---- 4. chat, per model
        models = [m.strip() for m in args.models.split(",") if m.strip()] or [answerer.model.name]
        report["models"] = {}
        client_cf = deps.get_cloudflare_client()
        for model in models:
            if model != answerer.model.name:
                if client_cf is None:
                    sys.exit("--models needs Cloudflare credentials in backend/.env")
                answerer.model = CloudflareChatModel(client_cf, model, timeout=settings.answer_timeout_seconds)
            print(f"\n=== Chat model: {answerer.model.name}")
            rows, latencies = [], []
            for q in questions:
                payload = {"book_id": book_id, "question": q["question"],
                           "interaction_type": q.get("interaction_type", "question")}
                if q.get("current_page"):
                    payload["reading_position"] = {"current_page": q["current_page"]}
                t = time.perf_counter()
                body = client.post("/api/v1/ai/chat", json=payload).json()
                elapsed = time.perf_counter() - t
                if body["provider_status"] not in ("no_evidence",):
                    latencies.append(elapsed)  # refusals before the model are not model latency
                row = {"id": q["id"], "type": q["type"], "seconds": round(elapsed, 2),
                       "pages": [c["source_location"] for c in body["citations"]],
                       "answer": body["answer"], **score(q, body)}
                rows.append(row)
                mark = "PASS" if row["correct"] else "FAIL"
                print(f"  {mark} {q['id']:<4} {row['answer_type']:<12} {elapsed:4.1f}s  {row['pages'][:3]}  "
                      f"{q['question'][:55]}")
                if args.show_answers or not row["correct"]:
                    print(f"         -> {body['answer'][:260]!r}")

            by_type: dict[str, list[bool]] = {}
            for row in rows:
                by_type.setdefault(row["type"], []).append(row["correct"])
            grounded = [r for r in rows if r["answer_type"] == "grounded"]
            summary = {
                "accuracy_by_type": {t: f"{sum(v)}/{len(v)}" for t, v in by_type.items()},
                "citation_validity": f"{sum(1 for r in grounded if r['pages'])}/{len(grounded)}",
                "provider_errors": sum(1 for r in rows if r["provider_status"] == "provider_error"),
                "latency_p50": round(statistics.median(latencies), 2) if latencies else None,
                "latency_p95": round(percentile(latencies, 95), 2) if latencies else None,
            }
            report["models"][answerer.model.name] = {"summary": summary, "rows": rows}
            print(f"  -> {json.dumps(summary)}")

        client.delete(f"/api/v1/books/{book_id}")

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReport written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
