"""Backward-compatible entry point.

The real app now lives in app/main.py (app.main:app). This shim exists
so `uvicorn main:app` (as documented in the original README) keeps
working for anyone with that command memorized.
"""
from app.main import app

__all__ = ["app"]
