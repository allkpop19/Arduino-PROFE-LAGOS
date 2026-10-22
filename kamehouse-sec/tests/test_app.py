import json
import threading
import time

from fastapi.testclient import TestClient

from app import create_app
from bridge import DemoBridge, DoorBridge


def credentials(client, password="1234"):
    return dict(password=password, challenge=client.get("/api/state").json()["challenge"])


def test_presence_alone_never_opens_and_password_is_checked():
    bridge = DemoBridge()
    with TestClient(create_app(bridge, "1234")) as client:
        assert client.get("/api/state").json()["challenge"] is None
        client.post("/api/demo/presence", json={"present": True})
        state = client.get("/api/state").json()
        assert state["present"] and not state["opened"] and state["challenge"]
        assert client.post("/api/unlock", json=credentials(client, "incorrecta")).status_code == 401
        assert not bridge.snapshot()["opened"]
        assert client.post("/api/unlock", json=credentials(client)).status_code == 200
        assert bridge.snapshot()["opened"]


def test_five_seconds_close_and_rearm_requires_departure(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("bridge.time.monotonic", lambda: clock[0])
    bridge = DemoBridge()
    bridge.set_present(True)
    assert bridge.open_door()
    clock[0] += 4.99
    assert bridge.snapshot()["opened"]
    clock[0] += 0.02
    assert not bridge.snapshot()["opened"]
    assert not bridge.open_door()
    bridge.set_present(False)
    bridge.set_present(True)
    assert bridge.open_door()


def test_stale_challenge_and_absent_person_rejected():
    bridge = DemoBridge()
    with TestClient(create_app(bridge, "1234")) as client:
        bridge.set_present(True)
        old = credentials(client)
        bridge.set_present(False)
        assert client.post("/api/unlock", json=old).status_code == 409
        bridge.set_present(True)
        assert client.post("/api/unlock", json=old).status_code == 409


def test_lockout_after_five_wrong_passwords():
    bridge = DemoBridge()
    bridge.set_present(True)
    with TestClient(create_app(bridge, "1234")) as client:
        for i in range(5):
            response = client.post("/api/unlock", json=credentials(client, "no"))
            assert response.status_code == (429 if i == 4 else 401)
        assert client.post("/api/unlock", json=credentials(client)).status_code == 429
        assert not bridge.snapshot()["opened"]


def test_origin_validation_static_files_and_no_config_exposure():
    bridge = DemoBridge()
    bridge.set_present(True)
    with TestClient(create_app(bridge, "1234")) as client:
        assert client.get("/").status_code == 200
        for file in ("app.js", "style.css", "theme.js"):
            assert client.get(f"/static/{file}").status_code == 200
        assert client.get("/config.json").status_code == 404
        assert client.post("/api/unlock", json=credentials(client), headers={"Origin":"http://evil.invalid"}).status_code == 403
        assert client.get("/api/state", headers={"Host":"evil.invalid"}).status_code == 400


def test_real_mode_has_no_demo_bypass():
    bridge = DoorBridge()
    # No conectar hardware en esta prueba.
    bridge.start = lambda: None
    bridge.stop = lambda: None
    with TestClient(create_app(bridge, "1234")) as client:
        assert client.post("/api/demo/presence", json={"present":True}).status_code == 404
        assert client.get("/api/state").json()["challenge"] is None


def report(**overrides):
    return dict(protocol="casa-v1", present=True, opened=False, needs_clear=False,
                remaining_ms=0, distance_cm=15, **overrides)


def test_serial_command_requires_real_ack_and_disconnect_blocks():
    bridge = DoorBridge("COM3")
    bridge._accept(report())

    class FakeSerial:
        def write(self, raw):
            request_id = raw.decode().strip().split()[1]
            # Confirmación asíncrona como la del lector serial.
            threading.Timer(0.01, lambda: bridge._accept(dict(
                protocol="casa-v1", present=True, opened=True, needs_clear=True,
                remaining_ms=5000, request_id=request_id, accepted=True))).start()

    bridge.connection = FakeSerial()
    assert bridge.open_door()
    assert bridge.snapshot()["opened"]
    assert not bridge.open_door()  # No duplicar apertura.
    bridge.last_seen = time.monotonic() - 3
    assert not bridge.snapshot()["connected"]
    assert not bridge.open_door()


def test_mismatched_firmware_is_not_a_connection():
    bridge = DoorBridge()
    bridge._accept({"protocol":"otro"})
    assert not bridge.snapshot()["connected"]


def test_serial_rejection_never_reports_success():
    bridge = DoorBridge("COM3")
    bridge._accept(report())

    class RejectSerial:
        def write(self, raw):
            request_id = raw.decode().strip().split()[1]
            bridge._accept(dict(protocol="casa-v1", present=False, opened=False,
                                needs_clear=False, remaining_ms=0,
                                request_id=request_id, accepted=False))

    bridge.connection = RejectSerial()
    assert not bridge.open_door()
    assert not bridge.snapshot()["opened"]
