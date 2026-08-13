"""Phase-driven orchestrator: single source of truth state machine.

LED COLOR SCHEME (granular feedback):
    idle                - Dim cyan breathing (waiting for wakeword)
    wakeword_detected   - Bright GREEN flash (acknowledged!)
    listening           - Bright BLUE sweep (capturing audio)
    transcribing        - PURPLE pulse (STT processing)
    thinking            - PINK pulse (LLM processing)
    tts_processing      - ORANGE pulse (generating speech)
    speaking            - Dark GREEN chase (playing audio)
    error               - RED blink (system error)
"""
from __future__ import annotations

import json
import random
import time
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, Optional

import zmq

from src.core.config_loader import load_config
from src.core.ipc import (
    TOPIC_CMD_LISTEN_START,
    TOPIC_CMD_LISTEN_STOP,
    TOPIC_CMD_PAUSE_VISION,
    TOPIC_CMD_VISN_CAPTURE,
    TOPIC_CMD_VISION_MODE,
    TOPIC_DISPLAY_STATE,
    TOPIC_DISPLAY_TEXT,
    TOPIC_ESP,
    TOPIC_HEALTH,
    TOPIC_LLM_REQ,
    TOPIC_LLM_RESP,
    TOPIC_NAV,
    TOPIC_REMOTE_EVENT,
    TOPIC_REMOTE_INTENT,
    TOPIC_REMOTE_SESSION,
    TOPIC_STT,
    TOPIC_TTS,
    TOPIC_VISN,
    TOPIC_VISN_CAPTURED,
    TOPIC_VISN_FRAME,
    TOPIC_WW_DETECTED,
    make_publisher,
    make_subscriber,
    publish_json,
)
from src.core.logging_setup import get_logger
from src.core.world_context import WorldContextAggregator

logger = get_logger("orchestrator", Path("logs"))


class Phase(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ERROR = auto()


class VisionMode(Enum):
    OFF = "off"
    ON_NO_STREAM = "on_no_stream"
    ON_WITH_STREAM = "on_with_stream"


class Orchestrator:
    TRANSITIONS = {
        (Phase.IDLE, "wakeword"): Phase.LISTENING,
        (Phase.IDLE, "auto_trigger"): Phase.LISTENING,
        (Phase.IDLE, "manual_trigger"): Phase.LISTENING,
        (Phase.IDLE, "manual_think"): Phase.THINKING,
        (Phase.IDLE, "manual_text"): Phase.THINKING,
        (Phase.LISTENING, "stt_valid"): Phase.THINKING,
        (Phase.LISTENING, "stt_invalid"): Phase.IDLE,
        (Phase.LISTENING, "stt_timeout"): Phase.IDLE,
        (Phase.THINKING, "llm_with_speech"): Phase.SPEAKING,
        (Phase.THINKING, "llm_no_speech"): Phase.IDLE,
        (Phase.THINKING, "llm_timeout"): Phase.IDLE,
        (Phase.SPEAKING, "tts_done"): Phase.IDLE,
        (Phase.SPEAKING, "tts_timeout"): Phase.IDLE,
        (Phase.IDLE, "health_error"): Phase.ERROR,
        (Phase.LISTENING, "health_error"): Phase.ERROR,
        (Phase.THINKING, "health_error"): Phase.ERROR,
        (Phase.SPEAKING, "health_error"): Phase.ERROR,
        (Phase.ERROR, "health_ok"): Phase.IDLE,
        (Phase.ERROR, "error_timeout"): Phase.IDLE,
    }

    def __init__(self) -> None:
        self.config = load_config(Path("config/system.yaml"))
        self.cmd_pub = make_publisher(self.config, channel="downstream", bind=True)
        self.events_sub = make_subscriber(self.config, channel="upstream", bind=True)
        self._world_context = WorldContextAggregator(self.config)
        self._world_context.start()
        self._phase = Phase.IDLE
        self._phase_entered_ts = time.time()
        self._last_interaction_ts = time.time()
        self._last_transcript = ""
        # Correlates llm.request with llm.response. Required because the
        # orchestrator gives up on a turn after llm.timeout_seconds while the
        # runner has no timeout of its own, so a very late reply could
        # otherwise be spoken as the answer to a different question -- and its
        # `direction` sent to the motors.
        self._llm_request_id: Optional[str] = None
        self._last_vision: Optional[Dict[str, Any]] = None
        self._last_nav_direction = "stop"
        self._vision_capture_pending: Optional[str] = None
        self._vision_capture_requested_ts: Optional[float] = None
        self._esp_obstacle = False
        self._esp_min_distance = -1
        self._obstacle_latched = False

        self._remote_session_active = False
        self._remote_last_seen = 0.0
        
        orch_cfg = self.config.get("orchestrator", {}) or {}
        self.auto_trigger_enabled = bool(orch_cfg.get("auto_trigger_enabled", True))
        self.auto_trigger_interval = float(orch_cfg.get("auto_trigger_interval", 60.0))
        
        stt_cfg = self.config.get("stt", {}) or {}
        self.stt_timeout_s = float(stt_cfg.get("timeout_seconds", 30.0))
        self.stt_min_confidence = float(stt_cfg.get("min_confidence", 0.3))
        self.error_recovery_s = 2.0

        # Watchdogs for the two phases that block on an external service
        # replying. Without them the FSM wedges permanently: every handler
        # early-returns when the phase is unexpected, so a hung LLM or a TTS
        # process that dies before publishing `done` leaves the robot deaf to
        # the wakeword until it is restarted by hand.
        llm_cfg = self.config.get("llm", {}) or {}
        self.llm_timeout_s = float(llm_cfg.get("timeout_seconds", 45.0))
        # Must exceed the longest utterance we ever synthesise, because `done`
        # only arrives after playback finishes.
        tts_cfg = self.config.get("tts", {}) or {}
        self.tts_timeout_s = float(tts_cfg.get("timeout_seconds", 60.0))

        remote_cfg = self.config.get("remote_interface", {}) or {}
        self.remote_session_timeout_s = float(remote_cfg.get("session_timeout_s", 15.0))

        vision_cfg = self.config.get("vision", {}) or {}
        default_mode = str(vision_cfg.get("default_mode", "off")).lower()
        self.vision_mode = self._coerce_vision_mode(default_mode)

    def _publish_led_state(self, state: str) -> None:
        publish_json(self.cmd_pub, TOPIC_DISPLAY_STATE, {
            "state": state,
            "phase": self._phase.name,
            "timestamp": int(time.time()),
            "source": "orchestrator",
        })
        logger.debug("LED: %s", state)

    def _publish_display_text(self, text: str) -> None:
        publish_json(self.cmd_pub, TOPIC_DISPLAY_TEXT, {
            "text": text,
            "timestamp": int(time.time()),
            "source": "orchestrator",
        })

    @property
    def phase(self) -> Phase:
        return self._phase

    def _transition(self, event_type: str) -> bool:
        key = (self._phase, event_type)
        next_phase = self.TRANSITIONS.get(key)
        if next_phase is None:
            logger.debug("IGNORED: event '%s' illegal in phase %s", event_type, self._phase.name)
            return False
        if next_phase == self._phase:
            return False
        old_phase = self._phase
        self._phase = next_phase
        self._phase_entered_ts = time.time()
        logger.info("PHASE: %s -> %s (event: %s)", old_phase.name, next_phase.name, event_type)
        return True

    @staticmethod
    def _normalize_direction(direction: Optional[str]) -> str:
        allowed = {"forward", "backward", "left", "right", "stop", "scan"}
        if not direction:
            return "stop"
        value = str(direction).strip().lower()
        return value if value in allowed else "stop"

    def _enter_listening(self, from_wakeword: bool = False) -> None:
        self._last_interaction_ts = time.time()
        if from_wakeword:
            self._publish_led_state("wakeword_detected")
            self._publish_display_text("Wakeword detected")
        else:
            self._publish_led_state("listening")
            self._publish_display_text("Listening...")
        if self.vision_mode != VisionMode.OFF:
            publish_json(self.cmd_pub, TOPIC_CMD_PAUSE_VISION, {"pause": True, "source": "orchestrator"})
        publish_json(self.cmd_pub, TOPIC_CMD_LISTEN_START, {"start": True, "source": "orchestrator"})

    def _exit_listening(self, reason: str) -> None:
        publish_json(self.cmd_pub, TOPIC_CMD_LISTEN_STOP, {"stop": True, "reason": reason, "source": "orchestrator"})
        if self.vision_mode != VisionMode.OFF:
            publish_json(self.cmd_pub, TOPIC_CMD_PAUSE_VISION, {"pause": False, "source": "orchestrator"})

    def _enter_thinking(
        self,
        text: str,
        vision: Optional[Dict[str, Any]] = None,
        *,
        source: str = "orchestrator",
        mode: Optional[str] = None,
    ) -> None:
        self._publish_led_state("thinking")
        self._publish_display_text(f"Heard: {text[:120]}")
        self._llm_request_id = f"llm-{int(time.time() * 1000)}"
        payload: Dict[str, Any] = {"text": text, "request_id": self._llm_request_id}
        if vision:
            payload["vision"] = vision
        payload["direction"] = self._last_nav_direction
        payload["world_context"] = self._world_context.get_snapshot()
        payload["context_note"] = "system_observation_only_last_known_state"
        payload["source"] = source
        if mode:
            payload["mode"] = mode
        publish_json(self.cmd_pub, TOPIC_LLM_REQ, payload)
        logger.info("LLM request text: %s", text[:120])

    def _publish_nav(self, direction: str, *, reason: Optional[str] = None) -> None:
        """Send a motion command.

        Every motion decision goes through here, including stops. An earlier
        version suppressed `stop` to avoid redundant traffic, which meant an
        explicit "obstacle ahead, stopping" decision was announced over TTS
        but never actually reached the motors.
        """
        message: Dict[str, Any] = {"direction": direction, "source": "orchestrator"}
        if reason:
            message["reason"] = reason
        publish_json(self.cmd_pub, TOPIC_NAV, message)
        self._last_nav_direction = direction

    def _enter_speaking(self, text: str, direction: Optional[str] = None) -> None:
        self._publish_led_state("tts_processing")
        self._publish_display_text(f"Saying: {text[:120]}")
        # `direction is None` means the reply carried no motion decision at all
        # (an ordinary conversational turn), so the motors are left as they are.
        if direction is not None:
            normalized = self._normalize_direction(direction)
            if self._esp_obstacle and normalized == "forward":
                logger.warning("Blocked forward command due to obstacle")
                self._publish_nav("stop", reason="obstacle")
            else:
                self._publish_nav(normalized)
        publish_json(self.cmd_pub, TOPIC_TTS, {"text": text, "source": "orchestrator"})

    def _enter_idle(self) -> None:
        self._publish_led_state("idle")
        self._publish_display_text("Idle")
        # Vision lifecycle is managed explicitly; do not auto-resume here.

    def _notify_failure(self, reason: str) -> None:
        feedback_messages = {
            "timeout": [
                "I didn't catch anything. Try again?",
                "I lost you there. Say it once more.",
                "I waited but heard nothing. Please try again.",
            ],
            "empty": [
                "I couldn't make that out. Please speak clearly.",
                "That came through empty. Try a bit louder.",
                "I missed that. Please repeat.",
            ],
            "low_confidence": [
                "I'm not sure I got that. Please repeat.",
                "That was unclear. Say it again for me.",
                "I didn't get enough confidence. Try again.",
            ],
            "llm_timeout": [
                "Sorry, I couldn't think of an answer in time.",
                "My brain took too long on that one. Try again?",
                "I timed out working that out. Please ask again.",
            ],
        }
        choices = feedback_messages.get(reason)
        if choices:
            message = random.choice(choices)
        else:
            message = "Something went wrong. Please try again."
        publish_json(self.cmd_pub, TOPIC_TTS, {"text": message, "notification": True, "source": "orchestrator"})
        logger.info("Failure feedback: %s", reason)

    def _emergency_stop(self, reason: str) -> None:
        """Fail-safe: an aborted turn must never leave the motors running."""
        self._publish_nav("stop", reason=reason)
        logger.warning("Emergency stop issued (reason=%s)", reason)

    def _force_error(self, reason: str) -> None:
        """Fault path: drop into ERROR from any phase and stop the motors.

        Deliberately bypasses TRANSITIONS: a fault has to be survivable from
        every phase including ERROR itself, and the existing error-recovery
        timer will return us to IDLE.
        """
        self._emergency_stop(reason)
        previous = self._phase
        self._phase = Phase.ERROR
        self._phase_entered_ts = time.time()
        self._publish_led_state("error")
        logger.error("PHASE: %s -> ERROR (fault: %s)", previous.name, reason)

    def on_wakeword(self, payload: Dict[str, Any]) -> None:
        if self._phase != Phase.IDLE:
            logger.debug("Wakeword ignored: not in IDLE (current: %s)", self._phase.name)
            return
        logger.info("Wakeword detected: %s", payload.get("keyword", "unknown"))
        if self._transition("wakeword"):
            self._enter_listening(from_wakeword=True)

    def on_manual_trigger(self, payload: Dict[str, Any]) -> None:
        if self._phase != Phase.IDLE:
            logger.debug("Manual trigger ignored: not in IDLE (current: %s)", self._phase.name)
            return
        logger.info("Manual trigger received")
        if self._transition("manual_trigger"):
            self._enter_listening(from_wakeword=False)

    def on_stt(self, payload: Dict[str, Any]) -> None:
        if self._phase != Phase.LISTENING:
            logger.debug("STT result ignored: not in LISTENING (current: %s)", self._phase.name)
            return
        text = str(payload.get("text", "")).strip()
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        logger.info("STT payload: text='%s' conf=%.2f", text[:120], confidence)
        
        if not text:
            logger.warning("Empty transcription received")
            self._exit_listening("empty")
            self._notify_failure("empty")
            self._transition("stt_invalid")
            self._enter_idle()
            return
        
        if confidence < self.stt_min_confidence:
            logger.info("Low confidence (%.3f < %.3f): '%s'", confidence, self.stt_min_confidence, text[:50])
            self._exit_listening("low_confidence")
            self._notify_failure("low_confidence")
            self._transition("stt_invalid")
            self._enter_idle()
            return
        
        logger.info("STT valid (%d chars, conf=%.2f)", len(text), confidence)
        self._last_transcript = text
        self._exit_listening("success")
        
        if self._transition("stt_valid"):
            if self._should_request_vision(text):
                self._request_vision_capture(text)
            else:
                self._enter_thinking(text)

    def _should_request_vision(self, text: str) -> bool:
        keywords = ["what do you see", "what are you seeing", "describe", "look at"]
        return any(k in text.lower() for k in keywords)

    def _request_vision_capture(self, text: str) -> None:
        if self.vision_mode == VisionMode.OFF:
            self._set_vision_mode(VisionMode.ON_NO_STREAM, source="internal")
        request_id = f"visn-{int(time.time() * 1000)}"
        self._vision_capture_pending = request_id
        self._vision_capture_requested_ts = time.time()
        self._last_transcript = text
        publish_json(self.cmd_pub, TOPIC_CMD_VISN_CAPTURE, {"request_id": request_id, "source": "orchestrator"})

    def _request_frame_capture(self, source: str) -> str:
        if self.vision_mode == VisionMode.OFF:
            self._set_vision_mode(VisionMode.ON_NO_STREAM, source=source)
        request_id = f"capture-{int(time.time() * 1000)}"
        publish_json(
            self.cmd_pub,
            TOPIC_CMD_VISN_CAPTURE,
            {"request_id": request_id, "source": source, "save": True, "purpose": "capture_frame"},
        )
        return request_id

    def on_vision(self, payload: Dict[str, Any]) -> None:
        self._last_vision = payload
        if self._vision_capture_pending:
            request_id = payload.get("request_id")
            if request_id == self._vision_capture_pending:
                self._vision_capture_pending = None
                self._vision_capture_requested_ts = None
                if self._phase == Phase.THINKING:
                    self._enter_thinking(self._last_transcript, vision=payload)

    def on_llm(self, payload: Dict[str, Any]) -> None:
        if self._phase != Phase.THINKING:
            logger.debug("LLM response ignored: not in THINKING (current: %s)", self._phase.name)
            return
        response_id = payload.get("request_id")
        if response_id is not None and response_id != self._llm_request_id:
            logger.warning(
                "Discarding stale llm.response (id=%s, current turn=%s)",
                response_id,
                self._llm_request_id,
            )
            return
        logger.info("LLM response received")
        body = payload.get("json") or {}
        speak = body.get("speak") or payload.get("text", "") or ""
        if not isinstance(speak, str):
            # The model is only asked for a JSON string here, but nothing
            # enforces it, and a non-string used to reach an f-string slice and
            # crash the process.
            logger.warning("LLM returned non-string speak (%s); coercing", type(speak).__name__)
            speak = str(speak)
        raw_direction = body.get("direction")
        direction = self._normalize_direction(raw_direction) if raw_direction is not None else None
        if self._esp_obstacle and direction == "forward":
            direction = "stop"
            if speak:
                speak = f"{speak} Obstacle ahead, stopping."
        logger.info("LLM response speak: %s", (speak or "")[:120])
        
        if speak:
            if self._transition("llm_with_speech"):
                self._enter_speaking(speak, direction)
        else:
            logger.info("LLM response has no speak text; TTS skipped")
            self._publish_remote_event("tts_skipped", {"reason": "empty_speak"})
            if direction is not None:
                self._publish_nav(direction)
            self._transition("llm_no_speech")
            self._enter_idle()

    def on_tts(self, payload: Dict[str, Any]) -> None:
        if payload.get("started"):
            self._publish_led_state("speaking")
            return
        done = payload.get("done") or payload.get("final") or payload.get("completed")
        if payload.get("notification"):
            return
        if not done:
            return
        if self._phase != Phase.SPEAKING:
            logger.debug("TTS done ignored: not in SPEAKING (current: %s)", self._phase.name)
            return
        logger.info("TTS completed")
        if self._transition("tts_done"):
            self._enter_idle()

    def on_esp(self, payload: Dict[str, Any]) -> None:
        data = payload.get("data")
        if data:
            self._esp_obstacle = bool(data.get("obstacle", False)) or (data.get("is_safe") is False)
            self._esp_min_distance = int(data.get("min_distance", -1))
            if self._esp_obstacle and not self._obstacle_latched:
                self._obstacle_latched = True
                logger.warning("Obstacle detected by ESP32; forcing stop")
                self._publish_nav("stop", reason="obstacle")
                self._publish_display_text("Obstacle detected - stopping")
            elif not self._esp_obstacle and self._obstacle_latched:
                self._obstacle_latched = False
                logger.info("Obstacle cleared by ESP32")
        alert = payload.get("alert")
        if alert == "COLLISION":
            logger.critical("ESP32 collision alert!")
            self._publish_nav("stop", reason="collision")

    def on_health(self, payload: Dict[str, Any]) -> None:
        ok = bool(payload.get("ok", True))
        if not ok and self._phase != Phase.ERROR:
            logger.error("Health error: %s", payload)
            self._publish_led_state("error")
            self._transition("health_error")
        elif ok and self._phase == Phase.ERROR:
            logger.info("Health restored")
            self._transition("health_ok")
            self._enter_idle()

    def _check_timeouts(self) -> None:
        now = time.time()
        elapsed = now - self._phase_entered_ts
        if self._phase == Phase.LISTENING and elapsed > self.stt_timeout_s:
            logger.warning("STT timeout (%.1fs)", self.stt_timeout_s)
            self._exit_listening("timeout")
            self._notify_failure("timeout")
            self._transition("stt_timeout")
            self._enter_idle()
        elif self._phase == Phase.THINKING and elapsed > self.llm_timeout_s:
            # No llm.response arrived. Stop moving (we are driving with an
            # unresponsive brain) and release the FSM so the next wakeword
            # is heard.
            logger.error("LLM timeout after %.1fs; releasing FSM", elapsed)
            self._emergency_stop("llm_timeout")
            self._notify_failure("llm_timeout")
            self._transition("llm_timeout")
            self._enter_idle()
        elif self._phase == Phase.SPEAKING and elapsed > self.tts_timeout_s:
            # Motors were commanded in _enter_speaking() and the completion
            # signal never came, so the stop is mandatory here.
            logger.error("TTS timeout after %.1fs; releasing FSM", elapsed)
            self._emergency_stop("tts_timeout")
            self._publish_display_text("Speech timed out. Ready.")
            self._transition("tts_timeout")
            self._enter_idle()
        elif self._phase == Phase.ERROR and elapsed > self.error_recovery_s:
            logger.info("Error auto-recovery after %.1fs", self.error_recovery_s)
            self._transition("error_timeout")
            self._publish_display_text("Recovered. Ready.")
            self._enter_idle()

        if self._vision_capture_pending and self._vision_capture_requested_ts:
            if (now - self._vision_capture_requested_ts) > 3.0:
                logger.warning("Vision capture timeout; proceeding without vision")
                self._vision_capture_pending = None
                self._vision_capture_requested_ts = None
                if self._phase == Phase.THINKING:
                    self._enter_thinking(self._last_transcript)

        if self._remote_session_active and self._remote_last_seen:
            if (now - self._remote_last_seen) > self.remote_session_timeout_s:
                self._remote_session_active = False
                publish_json(self.cmd_pub, TOPIC_REMOTE_SESSION, {
                    "active": False,
                    "last_seen": int(self._remote_last_seen) if self._remote_last_seen else None,
                    "source": "orchestrator",
                })

    def _check_auto_trigger(self) -> None:
        if not self.auto_trigger_enabled:
            return
        if self._phase != Phase.IDLE:
            return
        idle_time = time.time() - self._last_interaction_ts
        if idle_time > self.auto_trigger_interval:
            logger.info("Auto-trigger after %.1fs idle", idle_time)
            if self._transition("auto_trigger"):
                self._enter_listening(from_wakeword=False)

    def run(self) -> None:
        logger.info(
            "Orchestrator running (Phase FSM) auto_trigger=%s interval=%.1fs stt_timeout=%.1fs",
            self.auto_trigger_enabled,
            self.auto_trigger_interval,
            self.stt_timeout_s,
        )
        logger.info("Initial phase: %s", self._phase.name)
        self._publish_led_state("idle")
        self._set_vision_mode(self.vision_mode, source="internal")

        handlers = {
            TOPIC_WW_DETECTED: self.on_wakeword,
            TOPIC_CMD_LISTEN_START: self.on_manual_trigger,
            TOPIC_STT: self.on_stt,
            TOPIC_LLM_RESP: self.on_llm,
            TOPIC_TTS: self.on_tts,
            TOPIC_VISN: self.on_vision,
            TOPIC_ESP: self.on_esp,
            TOPIC_HEALTH: self.on_health,
            TOPIC_REMOTE_SESSION: self.on_remote_session,
            TOPIC_REMOTE_INTENT: self.on_remote_intent,
        }
        # Mirrored downstream so worker services and the remote interface can
        # observe them.
        #
        # This relay is the ONLY way any other process sees an upstream event:
        # upstream is a bound SUB, so a second SUB cannot connect to it and
        # receive anything. Adding a topic here is therefore what "let another
        # service subscribe to X" means in this architecture.
        #
        # llm.response is forwarded so the remote interface can show the last
        # spoken reply. Safe from loops: the LLM runner subscribes to
        # llm.request, never to its own response.
        forwarded = {TOPIC_VISN, TOPIC_VISN_CAPTURED, TOPIC_ESP, TOPIC_LLM_RESP}

        poller = zmq.Poller()
        poller.register(self.events_sub, zmq.POLLIN)

        while True:
            socks = dict(poller.poll(timeout=100))
            if self.events_sub in socks:
                try:
                    topic, data = self.events_sub.recv_multipart()
                    if topic == TOPIC_VISN_FRAME:
                        self.cmd_pub.send_multipart([topic, data])
                        continue
                    payload = json.loads(data)
                except Exception as exc:
                    logger.error("Recv/parse error: %s", exc)
                    continue

                handler = handlers.get(topic)
                if handler is not None:
                    try:
                        handler(payload)
                    except Exception:
                        # These calls used to sit outside any try block, so one
                        # malformed payload from any service killed the whole
                        # brain. Nothing a peer publishes may do that.
                        logger.exception("Handler for topic %r failed", topic)
                        self._force_error("handler_exception")
                if topic in forwarded:
                    publish_json(self.cmd_pub, topic, payload)

            self._check_timeouts()
            self._check_auto_trigger()

    def _coerce_vision_mode(self, raw: str) -> VisionMode:
        raw = (raw or "").lower().strip()
        if raw in {"off", "disabled", "false", "0"}:
            return VisionMode.OFF
        if raw in {"on_with_stream", "with_stream", "stream"}:
            return VisionMode.ON_WITH_STREAM
        return VisionMode.ON_NO_STREAM

    def _set_vision_mode(self, mode: VisionMode, *, source: str) -> None:
        if mode == self.vision_mode:
            return
        self.vision_mode = mode
        publish_json(
            self.cmd_pub,
            TOPIC_CMD_VISION_MODE,
            {"mode": mode.value, "timestamp": int(time.time()), "source": source},
        )

    @staticmethod
    def _payload_field(payload: Dict[str, Any], key: str) -> Any:
        """Read a field from the top level, falling back to ``extras``.

        The Android app nests command arguments under ``extras`` while this
        handler read them from the top level, so every `assistant_text` was
        rejected as missing_text. The app showed "accepted" regardless, because
        the HTTP layer returns 202 for any non-empty intent before the
        orchestrator ever sees it -- so the feature looked like it worked and
        silently did nothing.

        Accepting both shapes fixes it without requiring an app release.
        """
        value = payload.get(key)
        if value is not None:
            return value
        extras = payload.get("extras")
        if isinstance(extras, dict):
            return extras.get(key)
        return None

    def _publish_remote_event(self, event: str, payload: Dict[str, Any]) -> None:
        message = {"event": event, "timestamp": int(time.time()), **payload}
        publish_json(self.cmd_pub, TOPIC_REMOTE_EVENT, message)

    def on_remote_session(self, payload: Dict[str, Any]) -> None:
        active = bool(payload.get("active", False))
        self._remote_session_active = active
        if active:
            self._remote_last_seen = time.time()

    def on_remote_intent(self, payload: Dict[str, Any]) -> None:
        source = payload.get("source", "unknown")
        logger.info("remote_intent received source=%s payload=%s", source, payload)
        if source != "remote_app":
            logger.warning("remote_intent rejected reason=invalid_source payload=%s", payload)
            self._publish_remote_event("rejected", {"reason": "invalid_source", "payload": payload})
            return

        if not self._remote_session_active:
            logger.warning("remote_intent rejected reason=no_active_session payload=%s", payload)
            self._publish_remote_event("rejected", {"reason": "no_active_session", "payload": payload})
            return

        intent = str(payload.get("intent", "")).strip().lower()
        if not intent:
            logger.warning("remote_intent rejected reason=missing_intent payload=%s", payload)
            self._publish_remote_event("rejected", {"reason": "missing_intent", "payload": payload})
            return

        if intent in {"enable_vision", "enable_perception"}:
            self._set_vision_mode(VisionMode.ON_NO_STREAM, source="remote_app")
            logger.info("remote_intent accepted intent=%s", intent)
            self._publish_remote_event("accepted", {"intent": intent})
            return
        if intent in {"disable_vision", "disable_perception"}:
            self._set_vision_mode(VisionMode.OFF, source="remote_app")
            logger.info("remote_intent accepted intent=%s", intent)
            self._publish_remote_event("accepted", {"intent": intent})
            return
        if intent in {"enable_stream"}:
            self._set_vision_mode(VisionMode.ON_WITH_STREAM, source="remote_app")
            logger.info("remote_intent accepted intent=%s", intent)
            self._publish_remote_event("accepted", {"intent": intent})
            return
        if intent in {"disable_stream"}:
            self._set_vision_mode(VisionMode.ON_NO_STREAM, source="remote_app")
            logger.info("remote_intent accepted intent=%s", intent)
            self._publish_remote_event("accepted", {"intent": intent})
            return
        if intent in {"capture_frame"}:
            request_id = self._request_frame_capture("remote_app")
            logger.info("remote_intent accepted intent=%s request_id=%s", intent, request_id)
            self._publish_remote_event("accepted", {"intent": intent, "request_id": request_id})
            return
        if intent in {"invoke_assistant"}:
            if self._transition("manual_think"):
                text = str(self._payload_field(payload, "text") or "manual_invoke").strip() or "manual_invoke"
                self._last_transcript = text
                self._enter_thinking(text, source="remote_app", mode="manual_invoke")
                logger.info("remote_intent accepted intent=%s", intent)
                self._publish_remote_event("accepted", {"intent": intent})
            else:
                logger.warning("remote_intent rejected reason=busy payload=%s", payload)
                self._publish_remote_event("rejected", {"reason": "busy", "payload": payload})
            return
        if intent in {"assistant_text"}:
            text = str(self._payload_field(payload, "text") or "").strip()
            if not text:
                logger.warning("remote_intent rejected reason=missing_text payload=%s", payload)
                self._publish_remote_event("rejected", {"reason": "missing_text", "payload": payload})
                return
            if self._transition("manual_text"):
                self._last_transcript = text
                self._enter_thinking(text, source="remote_app", mode="manual_text")
                logger.info("remote_intent accepted intent=%s", intent)
                self._publish_remote_event("accepted", {"intent": intent})
            else:
                logger.warning("remote_intent rejected reason=busy payload=%s", payload)
                self._publish_remote_event("rejected", {"reason": "busy", "payload": payload})
            return
        if intent in {"scan", "start_scan"}:
            logger.info(
                "nav.command publish intent=%s direction=scan speed=%s duration=%s payload=%s",
                intent,
                payload.get("speed"),
                payload.get("duration"),
                {"direction": "scan", "source": "remote_app"},
            )
            publish_json(self.cmd_pub, TOPIC_NAV, {"direction": "scan", "source": "remote_app"})
            logger.info("remote_intent accepted intent=%s", intent)
            self._publish_remote_event("accepted", {"intent": intent})
            return
        if intent in {"stop", "stop_motion"}:
            logger.info(
                "nav.command publish intent=%s direction=stop speed=%s duration=%s payload=%s",
                intent,
                payload.get("speed"),
                payload.get("duration"),
                {"direction": "stop", "source": "remote_app"},
            )
            publish_json(self.cmd_pub, TOPIC_NAV, {"direction": "stop", "source": "remote_app"})
            logger.info("remote_intent accepted intent=%s", intent)
            self._publish_remote_event("accepted", {"intent": intent})
            return
        if intent in {"move_backward"}:
            logger.info(
                "nav.command publish intent=%s direction=backward speed=%s duration=%s payload=%s",
                intent,
                payload.get("speed"),
                payload.get("duration"),
                {"direction": "backward", "source": "remote_app"},
            )
            publish_json(self.cmd_pub, TOPIC_NAV, {"direction": "backward", "source": "remote_app"})
            logger.info("remote_intent accepted intent=%s direction=backward", intent)
            self._publish_remote_event("accepted", {"intent": intent, "direction": "backward"})
            return
        if intent in {"rotate", "rotate_left", "rotate_right", "start_motion", "start"}:
            direction = str(payload.get("direction", "")).strip().lower()
            if not direction:
                if intent == "rotate_left":
                    direction = "left"
                elif intent == "rotate_right":
                    direction = "right"
                elif intent in {"start_motion", "start"}:
                    direction = "forward"

            if direction not in {"forward", "backward", "left", "right"}:
                logger.warning("remote_intent rejected reason=invalid_direction payload=%s", payload)
                self._publish_remote_event("rejected", {"reason": "invalid_direction", "payload": payload})
                return
            logger.info(
                "nav.command publish intent=%s direction=%s speed=%s duration=%s payload=%s",
                intent,
                direction,
                payload.get("speed"),
                payload.get("duration"),
                {"direction": direction, "source": "remote_app"},
            )
            publish_json(self.cmd_pub, TOPIC_NAV, {"direction": direction, "source": "remote_app"})
            logger.info("remote_intent accepted intent=%s direction=%s", intent, direction)
            self._publish_remote_event("accepted", {"intent": intent, "direction": direction})
            return

        logger.warning("remote_intent rejected reason=unsupported_intent payload=%s", payload)
        self._publish_remote_event("rejected", {"reason": "unsupported_intent", "payload": payload})


def main() -> None:
    try:
        Orchestrator().run()
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        raise


if __name__ == "__main__":
    main()
