"""Servidor local: python -m uvicorn app:app --host 127.0.0.1 --port 8000"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from bridge import DemoBridge, DoorBridge
from storage import Store

BASE = Path(__file__).resolve().parent
COOKIE = "casa_admin"
SESSION_SECONDS = 900


class Password(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class Credentials(Password):
    challenge: str = Field(min_length=1, max_length=128)


class Presence(BaseModel):
    present: bool


class Preferences(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    sound_enabled: bool


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=4, max_length=128)
    confirmation: str = Field(min_length=4, max_length=128)


def create_app(bridge=None, password=None, data_dir=None):
    injected_bridge = bridge is not None
    config = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    runtime_password = (os.getenv("CASA_PASSWORD") or None) if password is None else None
    initial_password = password if password is not None else runtime_password or config["contrasena"]
    if not isinstance(initial_password, str) or not 1 <= len(initial_password) <= 128:
        raise ValueError("La contraseña debe tener entre 1 y 128 caracteres")
    if bridge is None:
        bridge = DemoBridge() if os.getenv("CASA_DEMO") == "1" else DoorBridge(
            os.getenv("CASA_PUERTO", config["puerto"]))
    mode = "demo" if isinstance(bridge, DemoBridge) else "real"
    if data_dir is None and injected_bridge:
        db_path = ":memory:"
    else:
        folder = Path(data_dir or os.getenv("CASA_DATOS", str(BASE / "datos")))
        folder.mkdir(parents=True, exist_ok=True)
        db_path = folder / "casa.sqlite3"
    store = Store(db_path, initial_password)

    def record(kind, message, event_id=None, created_at=None):
        try:
            store.add_event(kind, message, mode, event_id, created_at)
            store.error = None
        except (sqlite3.Error, OSError):
            store.error = "No se pudo guardar el historial. Revisa el espacio y los permisos de la carpeta datos."

    bridge.event_sink = lambda item: record(item["kind"], item["text"], item["id"], item["created_at"])

    @asynccontextmanager
    async def lifespan(app):
        record("info", "Aplicación iniciada" + (" · simulación" if mode == "demo" else ""))
        bridge.start()
        try:
            yield
        finally:
            bridge.stop()
            bridge.event_sink = None
            store.close()

    app = FastAPI(title="Casa conectada", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    allowed_hosts = ["127.0.0.1", "localhost", "testserver"]
    if mode == "demo":
        allowed_hosts.append("terminal.local")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    auth_lock = threading.RLock()
    auth = dict(challenge=None, busy=False, attempts=0, blocked_until=0.0)
    sessions = {}

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.netloc != request.headers.get("host") or parsed.scheme != request.url.scheme:
                    return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        return response

    def preferences():
        return dict(**store.preferences(), password_change_allowed=runtime_password is None)

    def blocked_seconds():
        return max(0, int(auth["blocked_until"] - time.monotonic() + 0.999))

    def verify(value):
        if runtime_password is not None:
            return hmac.compare_digest(value.encode(), runtime_password.encode())
        return store.verify_password(value)

    def check_password(value, context):
        if blocked_seconds():
            raise HTTPException(429, f"Espera {blocked_seconds()} segundos para volver a intentar")
        if not verify(value):
            auth["attempts"] += 1
            record("denied", f"Contraseña incorrecta · {context}")
            if auth["attempts"] >= 5:
                auth.update(attempts=0, blocked_until=time.monotonic() + 30)
                raise HTTPException(429, "Demasiados intentos. Espera 30 segundos")
            raise HTTPException(401, "Contraseña incorrecta")
        auth["attempts"] = 0

    def session_key(request):
        return hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()

    def authenticated(request):
        with auth_lock:
            now = time.monotonic()
            for key in list(sessions):
                if sessions[key] <= now:
                    sessions.pop(key, None)
            return session_key(request) in sessions

    def require_admin(request):
        if not authenticated(request):
            raise HTTPException(401, "Ingresa la contraseña para abrir la configuración")

    def current():
        state = bridge.snapshot()
        eligible = (state["connected"] and state["present"] and not state["opened"]
                    and not state["needs_clear"] and not auth["busy"])
        if not eligible:
            auth["challenge"] = None
        elif auth["challenge"] is None:
            auth["challenge"] = secrets.token_urlsafe(24)
        state.update(challenge=auth["challenge"], blocked_seconds=blocked_seconds(),
                     settings=preferences(), statistics=store.statistics(mode), storage_error=store.error)
        return state

    @app.get("/")
    def index():
        return FileResponse(BASE / "static" / "index.html")

    @app.get("/api/state")
    def state():
        with auth_lock:
            return current()

    @app.get("/api/history")
    def history(kind: Literal["all", "opened", "closed", "denied", "detected", "connection", "info"] = "all",
                day: date | None = Query(None, alias="date"), limit: int = Query(20, ge=1, le=50),
                offset: int = Query(0, ge=0)):
        return store.history(mode, kind, day, limit, offset)

    @app.post("/api/unlock")
    def unlock(credentials: Credentials):
        with auth_lock:
            status = current()
            if blocked_seconds():
                raise HTTPException(429, f"Espera {blocked_seconds()} segundos para volver a intentar")
            if not status["challenge"] or not hmac.compare_digest(credentials.challenge.encode(), status["challenge"].encode()):
                raise HTTPException(409, "La detección cambió. Acércate al sensor y vuelve a intentar")
            check_password(credentials.password, "acceso a la casa")
            auth.update(busy=True, challenge=None)
        try:
            if not bridge.open_door():
                record("info", "No se confirmó la apertura · revisar conexión y sensor")
                raise HTTPException(503, "El Arduino no confirmó la apertura. Revisa la conexión y el sensor")
            return {"ok": True}
        finally:
            with auth_lock:
                auth["busy"] = False

    @app.get("/api/admin/session")
    def admin_session(request: Request):
        return dict(authenticated=authenticated(request), settings=preferences())

    @app.post("/api/admin/login")
    def admin_login(data: Password, response: Response):
        with auth_lock:
            check_password(data.password, "configuración")
            token = secrets.token_urlsafe(32)
            if len(sessions) >= 128:
                sessions.pop(next(iter(sessions)))
            sessions[hashlib.sha256(token.encode()).hexdigest()] = time.monotonic() + SESSION_SECONDS
            response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="strict", path="/")
        return dict(ok=True, settings=preferences())

    @app.post("/api/admin/logout")
    def admin_logout(request: Request, response: Response):
        with auth_lock:
            sessions.pop(session_key(request), None)
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.post("/api/settings")
    def save_settings(data: Preferences, request: Request):
        with auth_lock:
            require_admin(request)
            name = data.name.strip()
            if not name or any(ord(char) < 32 for char in name):
                raise HTTPException(422, "Escribe un nombre válido para la casa")
            store.save_preferences(name, data.sound_enabled)
            record("info", "Nombre o preferencias de sonido actualizados")
            return dict(ok=True, settings=preferences())

    @app.post("/api/settings/password")
    def save_password(data: PasswordChange, request: Request, response: Response):
        with auth_lock:
            require_admin(request)
            if runtime_password is not None:
                raise HTTPException(409, "La contraseña está fijada por CASA_PASSWORD. Quita esa variable y reinicia para cambiarla aquí")
            if data.new_password != data.confirmation:
                raise HTTPException(422, "Las contraseñas nuevas no coinciden")
            check_password(data.current_password, "cambio de contraseña")
            store.change_password(data.new_password)
            sessions.clear()
            auth["challenge"] = None
            response.delete_cookie(COOKIE, path="/")
            record("info", "Contraseña de acceso cambiada")
        return {"ok": True}

    @app.post("/api/demo/presence")
    def demo_presence(data: Presence):
        if mode != "demo":
            raise HTTPException(404, "No disponible en modo real")
        bridge.set_present(data.present)
        with auth_lock:
            return current()

    return app


app = create_app()
