"""
The deployment entry point.

Vercel's Python runtime looks for a well-known file like `asgi.py` at the
root with a variable named `app` inside. The application itself lives in
gateway/main.py; this file merely points at it — so the platform's contract
does not get to dictate the code's layout.
"""

from gateway.main import app

__all__ = ["app"]
