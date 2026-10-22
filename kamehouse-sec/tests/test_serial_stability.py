import json
import serial

from bridge import DoorBridge


def frame():
    return json.dumps(dict(protocol="casa-v1", present=True, opened=False,
                           needs_clear=False, remaining_ms=0, distance_cm=5)).encode() + b"\n"


def test_delayed_start_and_fragmented_json_do_not_reopen_usb(monkeypatch):
    """Antes de esta corrección, la pausa inicial de 8 s reabría el COM."""
    clock = [100.0]
    monkeypatch.setattr("bridge.time.monotonic", lambda: clock[0])
    bridge = DoorBridge("COM3")
    raw = frame()
    chunks = [b""] * 8 + [raw[:35], raw[35:70], raw[70:], b""]
    opens, closes, during_silence = [], [], []

    class FakeSerial:
        def read_until(self, *args, **kwargs):
            clock[0] += 1
            if len(chunks) == 4:
                during_silence.append(bridge.snapshot())
            chunk = chunks.pop(0)
            if not chunks:
                bridge.stop_event.set()
            return chunk

        def close(self):
            closes.append(True)

    def factory(*args, **kwargs):
        opens.append(True)
        return FakeSerial()

    monkeypatch.setattr("bridge.serial.Serial", factory)
    bridge._run()
    assert len(opens) == 1
    assert len(closes) == 1  # Solo al terminar la prueba.
    assert during_silence[0]["usb_open"]
    assert not during_silence[0]["connected"]
    assert "sin datos válidos" in during_silence[0]["message"]
    assert bridge.last_seen > 108
    assert bridge.state["present"]
    assert any("Comunicación con Arduino lista" == e["text"] for e in bridge.events)


def test_reader_recovers_from_noise_oversized_lines_and_partial_messages():
    bridge = DoorBridge()
    bridge._feed_bytes(b"texto del arranque\n[]\n{\"protocol\":\"casa-v1\"}\n")
    bridge._feed_bytes(b"x" * 800 + b"\n")
    assert not bridge.snapshot()["connected"]
    raw = frame()
    bridge._feed_bytes(raw[:40])
    assert not bridge.snapshot()["connected"]
    bridge._feed_bytes(raw[40:-1])
    assert not bridge.snapshot()["connected"]
    bridge._feed_bytes(b"\n")
    assert bridge.snapshot()["connected"]
    assert bridge.snapshot()["distance_cm"] == 5


def test_real_usb_error_still_reconnects(monkeypatch):
    bridge = DoorBridge("COM3")
    # Acelerar solo el intervalo de reintento de esta prueba.
    monkeypatch.setattr(bridge.stop_event, "wait", lambda timeout: bridge.stop_event.is_set())
    opens, closes = [], []

    class FakeSerial:
        def __init__(self, broken):
            self.broken = broken

        def read_until(self, *args, **kwargs):
            if self.broken:
                raise serial.SerialException("cable desconectado")
            bridge.stop_event.set()
            return frame()

        def close(self):
            closes.append(True)

    def factory(*args, **kwargs):
        opens.append(True)
        return FakeSerial(broken=len(opens) == 1)

    monkeypatch.setattr("bridge.serial.Serial", factory)
    bridge._run()
    assert len(opens) == 2
    assert len(closes) == 2
    assert bridge.last_seen > 0
    assert any("Error USB:" in e["text"] for e in bridge.events)


def test_stale_data_cannot_open_even_while_usb_stays_open():
    bridge = DoorBridge("COM3")
    bridge._feed_bytes(frame())
    bridge.state["usb_open"] = True
    bridge.last_seen -= 3
    bridge.connection = object()
    state = bridge.snapshot()
    assert state["usb_open"] and not state["connected"]
    assert not bridge.open_door()
