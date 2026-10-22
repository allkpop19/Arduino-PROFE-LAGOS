"""Comunicación USB. No abre la puerta por detectar presencia."""
import json
import math
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import serial
from serial.tools import list_ports


class DoorBridge:
    def __init__(self, port="AUTO"):
        self.port = port
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.connection = None
        self.last_seen = 0.0
        self.pending = {}
        self.events = deque(maxlen=20)
        self.event_sink = None
        self.rx_buffer = bytearray()
        self.dropping_line = False
        self.state = dict(connected=False, present=False, opened=False,
                          needs_clear=False, remaining_ms=0, distance_cm=None,
                          port=None, usb_open=False, message="Buscando Arduino…", mode="real")

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.connection:
                self.connection.close()
        if self.thread:
            self.thread.join(timeout=2)

    def _event(self, text, kind="info"):
        item = dict(id=uuid.uuid4().hex, text=text, kind=kind, time=time.strftime("%H:%M:%S"),
                    created_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"))
        self.events.appendleft(item)
        if self.event_sink:
            self.event_sink(item)

    def snapshot(self):
        with self.lock:
            result = dict(self.state)
            # Ninguna apertura si dejó de llegar la señal del Arduino.
            result["connected"] = self.state["connected"] and time.monotonic() - self.last_seen < 2
            if self.state["connected"] and not result["connected"]:
                result["message"] = "USB abierto, esperando datos recientes del Arduino"
            result["events"] = list(self.events)
            result["last_seen_ms"] = int((time.monotonic() - self.last_seen) * 1000) if self.last_seen else None
            return result

    def _find_port(self):
        if self.port.upper() != "AUTO":
            return self.port
        ports = list(list_ports.comports())
        candidates = [p for p in ports if p.vid in (0x2341, 0x2A03, 0x1A86, 0x10C4)
                      or "arduino" in p.description.lower()]
        if len(candidates) == 1:
            return candidates[0].device
        if not candidates and len(ports) == 1:
            return ports[0].device
        if len(candidates) > 1 or len(ports) > 1:
            raise RuntimeError("Hay varios puertos: indica el COM del Arduino en config.json")
        raise RuntimeError("Conecta el Arduino por USB; no se encontró ningún puerto")

    def _accept(self, msg):
        if not isinstance(msg, dict) or msg.get("protocol") != "casa-v1":
            return False
        if any(type(msg.get(key)) is not bool for key in ("present", "opened", "needs_clear")):
            return False
        remaining = msg.get("remaining_ms")
        distance = msg.get("distance_cm")
        if type(remaining) is not int or not 0 <= remaining <= 5000:
            return False
        if distance is not None and (type(distance) not in (int, float)
                                     or not math.isfinite(distance) or distance < 0):
            return False
        with self.lock:
            old = dict(self.state)
            self.last_seen = time.monotonic()
            self.state.update(connected=True, present=bool(msg["present"]),
                              opened=bool(msg["opened"]), needs_clear=bool(msg["needs_clear"]),
                              remaining_ms=max(0, int(msg["remaining_ms"])),
                              distance_cm=msg.get("distance_cm"), message="Arduino conectado")
            if not old["connected"]:
                self._event("Comunicación con Arduino lista", "connection")
            if self.state["present"] and not old["present"]:
                self._event("Persona detectada frente a la casa", "detected")
            if self.state["opened"] and not old["opened"]:
                request_id = msg.get("request_id")
                if old["connected"] or (isinstance(request_id, str) and request_id in self.pending):
                    self._event("Contraseña aceptada · puerta abierta", "opened")
                else:
                    self._event("Puerta detectada abierta al conectar")
            if not self.state["opened"] and old["opened"]:
                self._event("Puerta cerrada automáticamente", "closed")
            request_id = msg.get("request_id")
            if isinstance(request_id, str) and request_id in self.pending:
                item = self.pending[request_id]
                item["accepted"] = msg.get("accepted") is True
                item["event"].set()
            return True

    def _feed_bytes(self, raw):
        """Conservar fragmentos hasta recibir la línea JSON completa."""
        for value in raw:
            if value == 10:
                line = bytes(self.rx_buffer)
                valid_line = not self.dropping_line
                self.rx_buffer.clear()
                self.dropping_line = False
                if valid_line and line.strip():
                    try:
                        self._accept(json.loads(line.decode("utf-8")))
                    except (ValueError, UnicodeError, OverflowError):
                        pass
            elif not self.dropping_line:
                if len(self.rx_buffer) < 511:
                    self.rx_buffer.append(value)
                else:
                    self.rx_buffer.clear()
                    self.dropping_line = True

    def _check_silence(self, started):
        # Falta de datos NO significa que el cable desapareció.
        # Mantener el COM abierto evita ciclos de reinicio por reapertura.
        with self.lock:
            latest = max(started, self.last_seen)
            if time.monotonic() - latest > 5:
                self.state.update(connected=False, message=(
                    "USB abierto, pero sin datos válidos. Carga casa.ino a 115200 "
                    "baudios y comprueba que sea la versión de este proyecto. "
                    "No se reiniciará el puerto."))

    def _run(self):
        while not self.stop_event.is_set():
            connection = None
            try:
                port = self._find_port()
                connection = serial.Serial(port, 115200, timeout=0.2, write_timeout=1)
                with self.lock:
                    self.connection = connection
                    self.last_seen = 0
                    self.rx_buffer.clear()
                    self.dropping_line = False
                    self.state.update(port=port, connected=False, present=False, usb_open=True,
                                      message="USB abierto. Esperando el programa de la casa…")
                    self._event(f"Puerto {port} abierto a 115200 baudios", "connection")
                started = time.monotonic()
                while not self.stop_event.is_set():
                    raw = connection.read_until(b"\n", size=512)
                    if raw:
                        self._feed_bytes(raw)
                    self._check_silence(started)
            except (serial.SerialException, OSError, RuntimeError) as exc:
                with self.lock:
                    self.state.update(connected=False, present=False, usb_open=False,
                                      message=f"{exc}. Reintentando…")
                    if not self.stop_event.is_set():
                        self._event(f"Error USB: {exc}", "connection")
            finally:
                with self.lock:
                    self.connection = None
                    self.state.update(connected=False, usb_open=False)
                    for item in self.pending.values():
                        item["event"].set()
                if connection:
                    connection.close()
            self.stop_event.wait(1.5)

    def open_door(self):
        request_id = uuid.uuid4().hex[:16]
        item = dict(event=threading.Event(), accepted=False)
        with self.lock:
            state = self.snapshot()
            if not (state["connected"] and state["present"] and not state["opened"]
                    and not state["needs_clear"] and self.connection):
                return False
            self.pending[request_id] = item
            try:
                self.connection.write(f"OPEN {request_id}\n".encode("ascii"))
            except (serial.SerialException, OSError):
                self.pending.pop(request_id, None)
                return False
        # El éxito se muestra solo tras la confirmación del Arduino.
        item["event"].wait(2)
        with self.lock:
            self.pending.pop(request_id, None)
            return item["accepted"]


class DemoBridge:
    """Simulación explícita sin abrir ningún puerto USB."""
    def __init__(self):
        self.lock = threading.RLock()
        self.present = False
        self.open_until = 0.0
        self.needs_clear = False
        self.events = deque(maxlen=20)
        self.event_sink = None
        self._event("Simulación iniciada · sin conexión a un servo real")

    def _event(self, text, kind="info"):
        item = dict(id=uuid.uuid4().hex, text=text, kind=kind, time=time.strftime("%H:%M:%S"),
                    created_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"))
        self.events.appendleft(item)
        if self.event_sink:
            self.event_sink(item)

    def start(self):
        pass

    def stop(self):
        pass

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            if self.open_until and now >= self.open_until:
                self.open_until = 0
                self._event("Puerta cerrada automáticamente", "closed")
            if not self.open_until and not self.present:
                self.needs_clear = False
            return dict(connected=True, present=self.present, opened=bool(self.open_until),
                        remaining_ms=max(0, int((self.open_until - now) * 1000)),
                        needs_clear=self.needs_clear, distance_cm=5 if self.present else 100,
                        port=None, message="Simulación · sin Arduino", mode="demo", events=list(self.events))

    def set_present(self, value):
        with self.lock:
            if value and not self.present:
                self._event("Persona detectada frente a la casa", "detected")
            self.present = value
            self.snapshot()

    def open_door(self):
        with self.lock:
            state = self.snapshot()
            if not state["present"] or state["opened"] or state["needs_clear"]:
                return False
            self.open_until = time.monotonic() + 5
            self.needs_clear = True
            self._event("Contraseña aceptada · puerta abierta", "opened")
            return True
