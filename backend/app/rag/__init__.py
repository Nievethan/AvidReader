"""Retrieval-augmented generation pipeline (owner: Umer).

Step order: extraction -> cleaning -> chunking -> embeddings -> vector store.
Everything here is plain functions/classes with no FastAPI dependency so it
can be unit-tested without the web app.

Spoiler boundary (see `models.Chunk.position`): page number for PDFs,
chapter (spine) number for EPUBs.
"""
