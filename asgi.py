"""
Dagitim girisi.

Vercel'in Python calisma ortami kok dizinde `asgi.py` gibi bilinen bir dosya
ve icinde `app` adli bir degisken ariyor. Uygulamanin kendisi gateway/main.py'de
duruyor; bu dosya yalnizca onu gosteriyor - platformun sozlesmesi kodun
duzenini belirlemesin diye.
"""

from gateway.main import app

__all__ = ["app"]
