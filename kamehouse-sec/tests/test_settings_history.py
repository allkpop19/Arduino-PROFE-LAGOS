import json
import time
from datetime import date, datetime

from fastapi.testclient import TestClient

from app import create_app
from bridge import DemoBridge
from storage import Store, TZ


def login(client, password="clave-prueba"):
    return client.post("/api/admin/login", json={"password": password})


def unlock(client, password="clave-prueba"):
    return client.post("/api/unlock", json={"password": password,
                       "challenge": client.get("/api/state").json()["challenge"]})


def test_initial_example_password_and_no_settings_without_authentication():
    bridge = DemoBridge()
    with TestClient(create_app(bridge)) as client:
        assert client.post("/api/settings", json={"name":"Mi casa", "sound_enabled":True}).status_code == 401
        assert login(client, "1234").status_code == 401
        response = login(client)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert client.get("/api/admin/session").json()["authenticated"]
        assert client.post("/api/settings", json={"name":"Casa de prueba", "sound_enabled":True}).status_code == 200
        settings = client.get("/api/state").json()["settings"]
        assert settings["name"] == "Casa de prueba" and settings["sound_enabled"]
        assert "password" not in settings
        client.post("/api/admin/logout")
        assert not client.get("/api/admin/session").json()["authenticated"]


def test_settings_and_new_password_survive_restart_and_revoke_sessions(tmp_path):
    app = create_app(DemoBridge(), data_dir=tmp_path)
    with TestClient(app) as client:
        assert login(client).status_code == 200
        other = TestClient(app)
        assert login(other).status_code == 200
        assert client.post("/api/settings", json={"name":"Casa de prueba", "sound_enabled":True}).status_code == 200
        assert client.post("/api/settings/password", json={"current_password":"no", "new_password":"9876", "confirmation":"9876"}).status_code == 401
        assert client.post("/api/settings/password", json={"current_password":"clave-prueba", "new_password":"9876", "confirmation":"8765"}).status_code == 422
        assert client.post("/api/settings/password", json={"current_password":"clave-prueba", "new_password":"9876", "confirmation":"9876"}).status_code == 200
        assert not client.get("/api/admin/session").json()["authenticated"]
        assert not other.get("/api/admin/session").json()["authenticated"]
        other.close()
    with TestClient(create_app(DemoBridge(), data_dir=tmp_path)) as client:
        assert login(client).status_code == 401
        assert login(client, "9876").status_code == 200
        settings = client.get("/api/state").json()["settings"]
        assert settings["name"] == "Casa de prueba" and settings["sound_enabled"]
        assert client.get("/datos/casa.sqlite3").status_code == 404


def test_persistent_history_statistics_filter_and_demo_separation(tmp_path):
    bridge = DemoBridge()
    with TestClient(create_app(bridge, data_dir=tmp_path)) as client:
        client.post("/api/demo/presence", json={"present":True})
        assert unlock(client, "mal").status_code == 401
        assert unlock(client).status_code == 200
        bridge.open_until = time.monotonic() - 1
        state = client.get("/api/state").json()
        assert state["statistics"]["openings_today"] == 1
        assert state["statistics"]["denied_today"] == 1
        assert state["statistics"]["last_entry"]
        assert client.get("/api/history?kind=opened").json()["total"] == 1
        assert client.get("/api/history?kind=denied").json()["total"] == 1
        assert client.get("/api/history?kind=closed").json()["total"] == 1
    app = create_app(DemoBridge(), data_dir=tmp_path)
    app.state.store.add_event("opened", "Solo modo real", "real")
    with TestClient(app) as client:
        history = client.get("/api/history").json()
        assert any(event["kind"] == "opened" for event in history["events"])
        assert all(event["mode"] == "demo" for event in history["events"])
        assert client.get("/api/state").json()["statistics"]["openings_today"] == 1


def test_history_date_timezone_pagination_and_invalid_queries():
    store = Store(":memory:", "clave-prueba")
    store.add_event("opened", "Hora de Chile", "real", created_at="2026-10-22T02:00:00.000000+00:00")
    assert store.history("real", day=date(2026,10,21))["total"] == 1
    assert store.history("real", day=date(2026,10,22))["total"] == 0
    store.close()
    app = create_app(DemoBridge())
    with TestClient(app) as client:
        for index in range(25):
            app.state.store.add_event("opened", f"Evento {index}", "demo")
        result = client.get("/api/history?kind=opened&limit=5&offset=5").json()
        assert result["total"] == 25 and len(result["events"]) == 5
        assert client.get("/api/history?kind=opened&date=" + datetime.now(TZ).date().isoformat()).json()["total"] == 25
        for query in ("kind=desconocido", "limit=100", "offset=-1", "date=no-es-fecha"):
            assert client.get("/api/history?" + query).status_code == 422


def test_admin_session_expires_and_password_changes_do_not_leak_secrets(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.time.monotonic", lambda: clock[0])
    app = create_app(DemoBridge())
    with TestClient(app) as client:
        assert login(client).status_code == 200
        clock[0] += 901
        assert not client.get("/api/admin/session").json()["authenticated"]
        assert client.post("/api/settings", json={"name":"Otra", "sound_enabled":False}).status_code == 401
        saved = json.loads(app.state.store.db.execute("SELECT value FROM settings WHERE key='password'").fetchone()[0])
        assert set(saved) == {"salt", "digest"}


def test_admin_bruteforce_shares_lockout_and_cross_origin_is_blocked():
    with TestClient(create_app(DemoBridge())) as client:
        for index in range(5):
            assert login(client, "no").status_code == (429 if index == 4 else 401)
        assert login(client).status_code == 429
        assert client.get("/api/state").json()["statistics"]["denied_today"] == 5
        assert client.post("/api/settings", json={"name":"No", "sound_enabled":True},
                           headers={"Origin":"http://otro.invalid"}).status_code == 403
