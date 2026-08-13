#!/usr/bin/env python3
"""Remote supervision interface (read-only status + intent commands).

Exposes HTTP endpoints bound to a private network address and translates
remote intents into internal IPC topics for the orchestrator.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import zmq

from src.core.config_loader import load_config
from src.core.ipc import (
    TOPIC_CMD_VISION_MODE,
    TOPIC_CMD_PAUSE_VISION,
    TOPIC_DISPLAY_STATE,
    TOPIC_DISPLAY_TEXT,
    TOPIC_ESP,
    TOPIC_HEALTH,
    TOPIC_LLM_RESP,
    TOPIC_REMOTE_EVENT,
    TOPIC_REMOTE_INTENT,
    TOPIC_REMOTE_SESSION,
    TOPIC_TTS,
    TOPIC_VISN,
    TOPIC_VISN_CAPTURED,
    TOPIC_VISN_FRAME,
    make_publisher,
    make_subscriber,
    publish_json,
)
from src.core.logging_setup import get_logger


class TelemetryState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.display_state: str = "unknown"
        self.display_text: str = ""
        self.vision_mode: str = "off"
        self.vision_paused: bool = False
        self.last_detection: Optional[Dict[str, Any]] = None
        self.detection_history: List[Dict[str, Any]] = []
        self.last_esp: Optional[Dict[str, Any]] = None
        self.last_alert: Optional[str] = None
        self.last_health: Optional[Dict[str, Any]] = None
        self.remote_session_active: bool = False
        self.remote_last_seen: float = 0.0
        self.last_remote_event: Optional[Dict[str, Any]] = None
        self.last_capture: Optional[Dict[str, Any]] = None
        self.last_llm_response: Optional[str] = None
        self.last_llm_ts: Optional[float] = None
        self.last_tts_text: Optional[str] = None
        self.last_tts_status: Optional[str] = None
        self.last_tts_ts: Optional[float] = None

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            safety_stop = False
            motor_enabled: Optional[bool] = None
            motor: Optional[Dict[str, Any]] = None
            min_distance: Optional[int] = None
            obstacle = False
            warning = False
            if self.last_esp and "data" in self.last_esp:
                data = self.last_esp["data"] or {}
                obstacle = bool(data.get("obstacle", False))
                warning = bool(data.get("warning", False))
                min_distance = data.get("min_distance")
                is_safe = data.get("is_safe")
                if isinstance(is_safe, bool):
                    motor_enabled = is_safe
                lmotor = data.get("lmotor")
                rmotor = data.get("rmotor")
                if lmotor is not None or rmotor is not None:
                    motor = {
                        "left": lmotor,
                        "right": rmotor,
                        "ts": self.last_esp.get("data_ts"),
                    }
            if obstacle or warning or (self.last_alert is not None):
                safety_stop = True

            stream_url = "/stream/mjpeg" if self.vision_mode == "on_with_stream" else None
            return {
                "remote_session_active": self.remote_session_active,
                "remote_last_seen": int(self.remote_last_seen) if self.remote_last_seen else None,
                "mode": self.display_state,
                "display_text": self.display_text,
                "vision_mode": self.vision_mode,
                "stream_url": stream_url,
                "vision_active": self.vision_mode != "off",
                "vision_paused": self.vision_paused,
                "motor_enabled": motor_enabled,
                "motor": motor,
                "safety_stop": safety_stop,
                "safety_alert": self.last_alert,
                "sensor": self.last_esp.get("data") if self.last_esp else None,
                "sensor_ts": self.last_esp.get("data_ts") if self.last_esp else None,
                "sensor_buffer": self.last_esp.get("buffer") if self.last_esp else None,
                "vision_last_detection": self.last_detection,
                "detection_history": list(self.detection_history),
                "last_capture": self.last_capture,
                "last_llm_response": self.last_llm_response,
                "last_llm_ts": int(self.last_llm_ts) if self.last_llm_ts else None,
                "last_tts_text": self.last_tts_text,
                "last_tts_status": self.last_tts_status,
                "last_tts_ts": int(self.last_tts_ts) if self.last_tts_ts else None,
                "health": self.last_health,
                "remote_event": self.last_remote_event,
            }


class RemoteSupervisor:
    def __init__(self, config_path: Path) -> None:
        self.config = load_config(config_path)
        log_dir = Path(self.config.get("logs", {}).get("directory", "logs"))
        if not log_dir.is_absolute():
            log_dir = Path.cwd() / log_dir
        self.log_dir = log_dir
        self.logger = get_logger("remote.interface", log_dir)

        remote_cfg = self.config.get("remote_interface", {}) or {}
        self.bind_host = remote_cfg.get("bind_host", "127.0.0.1")
        self.bind_port = int(remote_cfg.get("port", 8770))
        self.allowed_cidrs = self._parse_cidrs(remote_cfg.get("allowed_cidrs", ["100.64.0.0/10"]))
        # Shared secret, checked before the source-IP allowlist.
        #
        # IP allowlisting stops working the moment this service sits behind any
        # NAT -- notably a Docker published port, where every request arrives
        # from the bridge gateway (172.x.x.x) and the real client is
        # unknowable. The allowlist then cannot distinguish a tailnet peer from
        # anyone who can reach the port, on an endpoint that commands motors.
        #
        # Optional so existing deployments keep working, but startup warns
        # loudly when it is unset. Env var, never config, so it cannot be
        # committed by accident.
        self.auth_token = os.environ.get("REMOTE_AUTH_TOKEN", "").strip()
        self.session_timeout_s = float(remote_cfg.get("session_timeout_s", 15.0))
        self._detection_history_max = int(remote_cfg.get("detection_history_max", 200))

        self.telemetry = TelemetryState()
        self._ctx = zmq.Context.instance()
        self._pub = make_publisher(self.config, channel="upstream")
        self._sub_down = make_subscriber(self.config, channel="downstream")

        # All telemetry comes from the downstream channel.
        #
        # There was a second subscriber on `upstream` carrying esp32.raw,
        # system.health, llm.response and remote.event. It never received
        # anything: the orchestrator BINDS a SUB on upstream, and a SUB that
        # connects to a bound SUB is a SUB-to-SUB pairing, which ZMTP refuses.
        # Verified against libzmq 4.3.5 -- 0 of 20 messages delivered.
        #
        # That is why /status has always reported sensor, motor, safety_stop
        # and last_llm_response as null, and why last_tts_status never advanced
        # past "queued". The vision fields worked only because the orchestrator
        # happens to re-publish those downstream.
        for topic in [
            TOPIC_ESP,
            TOPIC_HEALTH,
            TOPIC_LLM_RESP,
            TOPIC_REMOTE_EVENT,
            TOPIC_DISPLAY_STATE,
            TOPIC_DISPLAY_TEXT,
            TOPIC_CMD_VISION_MODE,
            TOPIC_CMD_PAUSE_VISION,
            TOPIC_VISN,
            TOPIC_VISN_FRAME,
            TOPIC_VISN_CAPTURED,
            TOPIC_TTS,
        ]:
            self._sub_down.setsockopt(zmq.SUBSCRIBE, topic)

        self._poller = zmq.Poller()
        self._poller.register(self._sub_down, zmq.POLLIN)

        self._running = True
        self._last_session_emit = False
        self._stream_lock = threading.Condition()
        self._latest_frame: Optional[bytes] = None
        self._latest_frame_ts: float = 0.0
        self._log_services = {
            "remote_interface": ["remote.interface.log", "remote-interface.log"],
            "orchestrator": ["orchestrator.log"],
            "uart": ["uart.motor_bridge.log", "uart.bridge.log", "uart.log"],
            "vision": ["vision.log", "vision.runner.log"],
            "llm_tts": [
                "llm.azure_openai.log",
                "llm.gemini.log",
                "llm.local.log",
                "tts.azure.log",
                "tts.piper.log",
                "tts.log",
            ],
        }

    def _tail_lines(self, path: Path, max_lines: int) -> List[str]:
        if max_lines <= 0:
            return []
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                buffer = deque(handle, maxlen=max_lines)
            return [line.rstrip("\n") for line in buffer]
        except FileNotFoundError:
            return []
        except OSError:
            return []

    def _fetch_logs(self, service: str, max_lines: int) -> Optional[Dict[str, Any]]:
        filenames = self._log_services.get(service)
        if not filenames:
            return None
        files = []
        for name in filenames:
            path = self.log_dir / name
            if path.exists():
                files.append(path)
        if not files:
            return {
                "service": service,
                "lines": [],
                "sources": [str(self.log_dir / name) for name in filenames],
                "ts": int(time.time()),
                "error": "log_files_missing",
            }
        merged: List[str] = []
        sources: List[str] = []
        for path in files:
            sources.append(str(path))
            lines = self._tail_lines(path, max_lines)
            if len(files) > 1:
                merged.extend([f"[{path.name}] {line}" for line in lines])
            else:
                merged.extend(lines)
        return {
            "service": service,
            "lines": merged[-max_lines:],
            "sources": sources,
            "ts": int(time.time()),
        }

    @staticmethod
    def _parse_cidrs(raw: Any) -> List[Any]:
        cidrs = raw if isinstance(raw, list) else [raw]
        nets = []
        for entry in cidrs:
            if not entry:
                continue
            try:
                nets.append(ip_network(str(entry)))
            except ValueError:
                continue
        return nets

    def _client_allowed(self, client_ip: str) -> bool:
        if not self.allowed_cidrs:
            # Fail closed. POST /intent can command motion, and _parse_cidrs
            # silently drops unparseable entries -- so a single typo in
            # remote_interface.allowed_cidrs used to turn motion control into
            # an unauthenticated open endpoint, on 0.0.0.0 by default.
            self.logger.error(
                "No usable allowed_cidrs configured; refusing client %s", client_ip
            )
            return False
        try:
            addr = ip_address(client_ip)
        except ValueError:
            return False
        return any(addr in net for net in self.allowed_cidrs)

    def _touch_session(self) -> None:
        now = time.time()
        with self.telemetry.lock:
            self.telemetry.remote_last_seen = now
            self.telemetry.remote_session_active = True

    def _publish_session_state(self) -> None:
        with self.telemetry.lock:
            active = self.telemetry.remote_session_active
            last_seen = self.telemetry.remote_last_seen
        publish_json(
            self._pub,
            TOPIC_REMOTE_SESSION,
            {
                "active": bool(active),
                "last_seen": int(last_seen) if last_seen else None,
                "source": "remote_app",
            },
        )

    def _session_watchdog(self) -> None:
        while self._running:
            now = time.time()
            with self.telemetry.lock:
                active = self.telemetry.remote_session_active
                last_seen = self.telemetry.remote_last_seen
            if active and last_seen and (now - last_seen) > self.session_timeout_s:
                with self.telemetry.lock:
                    self.telemetry.remote_session_active = False
                self._publish_session_state()
            time.sleep(1.0)

    def _telemetry_loop(self) -> None:
        while self._running:
            events = dict(self._poller.poll(timeout=200))
            if self._sub_up in events:
                self._drain_socket(self._sub_up)
            if self._sub_down in events:
                self._drain_socket(self._sub_down)

    def _drain_socket(self, sock: zmq.Socket) -> None:
        while True:
            try:
                topic, raw = sock.recv_multipart(flags=zmq.NOBLOCK)
            except zmq.Again:
                break
            if topic == TOPIC_VISN_FRAME:
                with self._stream_lock:
                    self._latest_frame = raw
                    self._latest_frame_ts = time.time()
                    self._stream_lock.notify_all()
                continue

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            with self.telemetry.lock:
                if topic == TOPIC_DISPLAY_STATE:
                    self.telemetry.display_state = str(payload.get("state", "unknown"))
                elif topic == TOPIC_DISPLAY_TEXT:
                    self.telemetry.display_text = str(payload.get("text", ""))
                elif topic == TOPIC_CMD_VISION_MODE:
                    self.telemetry.vision_mode = str(payload.get("mode", "off"))
                elif topic == TOPIC_CMD_PAUSE_VISION:
                    self.telemetry.vision_paused = bool(payload.get("pause", False))
                elif topic == TOPIC_VISN:
                    self.telemetry.last_detection = payload
                    label = str(payload.get("label", ""))
                    if label and label != "none":
                        entry = {
                            "label": label,
                            "bbox": payload.get("bbox"),
                            "confidence": payload.get("confidence"),
                            "ts": payload.get("ts"),
                        }
                        self.telemetry.detection_history.append(entry)
                        if len(self.telemetry.detection_history) > self._detection_history_max:
                            self.telemetry.detection_history = self.telemetry.detection_history[-self._detection_history_max:]
                elif topic == TOPIC_ESP:
                    self.telemetry.last_esp = payload
                    alert = payload.get("alert")
                    if alert:
                        self.telemetry.last_alert = str(alert)
                    if payload.get("blocked"):
                        self.telemetry.last_alert = str(payload.get("reason", "blocked"))
                elif topic == TOPIC_HEALTH:
                    self.telemetry.last_health = payload
                elif topic == TOPIC_REMOTE_EVENT:
                    self.telemetry.last_remote_event = payload
                elif topic == TOPIC_VISN_CAPTURED:
                    self.telemetry.last_capture = payload
                elif topic == TOPIC_LLM_RESP:
                    body = payload.get("json") or {}
                    speak = body.get("speak") or payload.get("text") or payload.get("raw")
                    if speak:
                        self.telemetry.last_llm_response = str(speak)[:240]
                        self.telemetry.last_llm_ts = time.time()
                elif topic == TOPIC_TTS:
                    if payload.get("text"):
                        self.telemetry.last_tts_text = str(payload.get("text"))[:240]
                        self.telemetry.last_tts_status = "queued"
                        self.telemetry.last_tts_ts = time.time()
                    if payload.get("started"):
                        self.telemetry.last_tts_status = "started"
                        self.telemetry.last_tts_ts = time.time()
                    if payload.get("done") or payload.get("final") or payload.get("completed"):
                        self.telemetry.last_tts_status = "done"
                        self.telemetry.last_tts_ts = time.time()

    def serve(self) -> None:
        threading.Thread(target=self._telemetry_loop, daemon=True).start()
        threading.Thread(target=self._session_watchdog, daemon=True).start()

        handler = self._make_handler()
        server = ThreadingHTTPServer((self.bind_host, self.bind_port), handler)
        self.logger.info("Remote interface listening on %s:%s", self.bind_host, self.bind_port)
        if self.auth_token:
            self.logger.info("Auth: bearer token required")
        else:
            self.logger.warning(
                "Auth: source-IP allowlist only (%s). POST /intent commands the "
                "motors, so set REMOTE_AUTH_TOKEN -- and note the allowlist is "
                "meaningless behind NAT, including a Docker published port, "
                "where every request appears to come from the bridge gateway.",
                [str(net) for net in self.allowed_cidrs] or "EMPTY",
            )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            server.server_close()

    def _make_handler(self):
        supervisor = self

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _read_json(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    supervisor.logger.warning("Remote interface received invalid JSON")
                    return {}

            def _allowed(self) -> bool:
                # A valid token is sufficient on its own: it is the only check
                # that still means anything once the service is behind NAT.
                if supervisor.auth_token:
                    header = self.headers.get("Authorization", "")
                    presented = header[7:] if header.startswith("Bearer ") else ""
                    if compare_digest(presented, supervisor.auth_token):
                        return True
                    supervisor.logger.warning(
                        "Remote interface rejected request from %s: bad or missing token",
                        self.client_address[0],
                    )
                    return False

                client_ip = self.client_address[0]
                if supervisor._client_allowed(client_ip):
                    return True
                supervisor.logger.warning("Remote interface rejected IP %s", client_ip)
                return False

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                # /health is deliberately unauthenticated. It is a liveness
                # probe for container orchestration and monitoring, it returns
                # nothing beyond "this process is up", and an open port already
                # reveals that much. Requiring a token here just means the
                # healthcheck reports the service as dead while it is fine.
                if parsed.path != "/health" and not self._allowed():
                    self._send_json(403, {"error": "forbidden"})
                    return
                if parsed.path == "/stream/mjpeg":
                    with supervisor.telemetry.lock:
                        vision_mode = supervisor.telemetry.vision_mode
                    if vision_mode != "on_with_stream":
                        self._send_json(409, {"error": "stream_disabled"})
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        while True:
                            with supervisor.telemetry.lock:
                                if supervisor.telemetry.vision_mode != "on_with_stream":
                                    break
                            with supervisor._stream_lock:
                                if supervisor._latest_frame is None:
                                    supervisor._stream_lock.wait(timeout=1.0)
                                frame = supervisor._latest_frame
                            if frame is None:
                                continue
                            self.wfile.write(b"--frame\r\n")
                            self.wfile.write(b"Content-Type: image/jpeg\r\n")
                            self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("utf-8"))
                            self.wfile.write(frame)
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    except Exception as exc:  # pragma: no cover - defensive
                        supervisor.logger.info("Stream closed: %s", exc)
                    return
                if parsed.path in {"/status", "/telemetry"}:
                    supervisor._touch_session()
                    supervisor._publish_session_state()
                    self._send_json(200, supervisor.telemetry.snapshot())
                    return
                if parsed.path == "/health":
                    self._send_json(200, {"ok": True, "timestamp": int(time.time())})
                    return
                if parsed.path == "/logs":
                    qs = parse_qs(parsed.query or "")
                    service = (qs.get("service") or qs.get("name") or [None])[0]
                    try:
                        requested = int((qs.get("lines") or ["100"])[0])
                    except ValueError:
                        requested = 100
                    max_lines = max(10, min(500, requested))
                    if not service:
                        self._send_json(200, {"services": list(supervisor._log_services.keys())})
                        return
                    payload = supervisor._fetch_logs(str(service), max_lines)
                    if payload is None:
                        self._send_json(404, {"error": "unknown_service"})
                        return
                    self._send_json(200, payload)
                    return
                log = getattr(supervisor, "logger", None)
                if log:
                    log.warning("/intent rejected reason=bad_path path=%s ts=%s", self.path, time.time())
                self._send_json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                if not self._allowed():
                    log = getattr(supervisor, "logger", None)
                    if log:
                        log.warning("/intent rejected reason=forbidden ip=%s ts=%s", self.client_address[0], time.time())
                    self._send_json(403, {"error": "forbidden"})
                    return

                if self.path == "/intent":
                    payload = self._read_json()
                    intent = str(payload.get("intent", "")).strip()
                    if not intent:
                        log = getattr(supervisor, "logger", None)
                        if log:
                            log.warning("/intent rejected reason=missing_intent ts=%s payload=%s", time.time(), payload)
                        self._send_json(400, {"error": "missing_intent"})
                        return

                    supervisor._touch_session()
                    supervisor._publish_session_state()

                    intent_payload = {
                        **payload,
                        "intent": intent,
                        "source": "remote_app",
                        "timestamp": int(time.time()),
                    }
                    log = getattr(supervisor, "logger", None)
                    if log:
                        log.info("/intent received ts=%s payload=%s", time.time(), intent_payload)
                        log.info("ipc publish topic=%s ts=%s", TOPIC_REMOTE_INTENT, time.time())
                    publish_json(supervisor._pub, TOPIC_REMOTE_INTENT, intent_payload)
                    self._send_json(202, {"accepted": True, "intent": intent})
                    return

                log = getattr(supervisor, "logger", None)
                if log:
                    log.warning("/intent rejected reason=bad_path path=%s ts=%s", self.path, time.time())
                self._send_json(404, {"error": "not_found"})

            def log_message(self, format: str, *args) -> None:
                supervisor.logger.info("remote.http %s - %s", self.client_address[0], format % args)

        return Handler


def main() -> None:
    supervisor = RemoteSupervisor(Path("config/system.yaml"))
    supervisor.serve()


if __name__ == "__main__":
    main()
