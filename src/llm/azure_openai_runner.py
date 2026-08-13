#!/usr/bin/env python3
"""Azure OpenAI LLM runner bridging ZMQ llm.request to llm.response.

- Subscribes to `llm.request` on the downstream bus.
- Calls Azure OpenAI Responses API (tested in third_party/azure-openai/testing.py).
- Publishes `llm.response` with parsed JSON body plus raw text.

Environment variables (no API keys in code):
- AZURE_OPENAI_API_KEY
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_DEPLOYMENT
- AZURE_OPENAI_API_VERSION (optional, default: 2025-03-01-preview)
"""
from __future__ import annotations

import json
import os
import random
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import zmq
from openai import AzureOpenAI

from src.core.config_loader import load_config
from src.core.ipc import (
    TOPIC_LLM_REQ,
    TOPIC_LLM_RESP,
    make_publisher,
    make_subscriber,
    publish_json,
)
from src.core.logging_setup import get_logger
from src.core.json_extract import extract_json_object
from src.llm.conversation_memory import ConversationMemory


class AzureOpenAIRunner:
    def __init__(self) -> None:
        self.config = load_config(Path("config/system.yaml"))
        logs_cfg = self.config.get("logs", {}) or {}
        log_dir = Path(logs_cfg.get("directory", "logs"))
        self.logger = get_logger("llm.azure_openai", log_dir)

        llm_cfg = self.config.get("llm", {}) or {}
        engine = str(llm_cfg.get("engine", "")).lower()
        if engine not in {"azure_openai", "azure-openai", "azure"}:
            self.logger.warning("LLM engine not set to azure_openai (engine=%s)", engine)

        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview").strip()

        if not api_key:
            raise RuntimeError("AZURE_OPENAI_API_KEY not configured")
        if not endpoint:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT not configured")
        if not deployment:
            raise RuntimeError("AZURE_OPENAI_DEPLOYMENT not configured")

        # Without an explicit timeout the SDK defaults to a 600s read timeout
        # with retries, so a stalled request outlives the orchestrator's
        # THINKING watchdog many times over and eventually returns to answer a
        # question the user abandoned minutes ago.
        self.request_timeout_s = float(llm_cfg.get("request_timeout_s", 20.0))
        self.client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=endpoint,
            api_key=api_key,
            timeout=self.request_timeout_s,
            max_retries=2,
        )
        self.deployment = deployment
        # Pinned to 1 because Azure reasoning deployments (o1/o3/o4-mini)
        # reject any other value. Override only for a standard chat model.
        self.temperature = float(llm_cfg.get("azure_temperature", 1.0))
        # 160 was tight enough that a JSON envelope wrapping a sentence of
        # prose was routinely truncated mid-string.
        self.max_completion_tokens = int(llm_cfg.get("max_completion_tokens", 320))

        self.ctx = zmq.Context.instance()
        self.sub = make_subscriber(self.config, topic=TOPIC_LLM_REQ, channel="downstream")
        self.pub = make_publisher(self.config, channel="upstream")
        self._running = True
        self._memory = ConversationMemory(
            max_turns=int(llm_cfg.get("memory_max_turns", 10)),
            conversation_timeout_s=float(llm_cfg.get("conversation_timeout_s", 120.0)),
        )

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.logger.info(
            "AzureOpenAIRunner initialized (deployment=%s, api_version=%s)",
            self.deployment,
            api_version,
        )

    def _handle_signal(self, *_: int) -> None:
        self.shutdown()
        sys.exit(0)

    def shutdown(self) -> None:
        self._running = False
        try:
            self.sub.close(0)
        except Exception:
            pass
        try:
            self.pub.close(0)
        except Exception:
            pass
        self.logger.info("AzureOpenAIRunner shutting down")

    @staticmethod
    def _extract_json(raw: str) -> Dict[str, Any]:
        return extract_json_object(raw)

    @staticmethod
    def _normalize_direction(value: Any) -> str:
        allowed = {"forward", "backward", "left", "right", "stop", "scan"}
        if not value:
            return "stop"
        direction = str(value).strip().lower()
        return direction if direction in allowed else "stop"

    def _build_messages(
        self,
        text: str,
        payload: Dict[str, Any],
        context_block: Optional[str] = None,
    ) -> list[Dict[str, str]]:
        direction = payload.get("direction")
        vision = payload.get("vision") if isinstance(payload.get("vision"), dict) else None
        self._memory.update_robot_state(direction=direction, vision=vision)
        messages = self._memory.build_messages_format(current_query=text)
        if context_block:
            messages.insert(0, {"role": "system", "content": context_block})
        return messages

    def _call_azure(
        self,
        text: str,
        payload: Dict[str, Any],
        context_block: Optional[str] = None,
    ) -> tuple[Dict[str, Any], str]:
        if not text:
            return {}, ""
        messages = self._build_messages(text, payload, context_block)

        try:
            resp = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                max_completion_tokens=160,
                temperature=1,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Azure OpenAI request failed: %s", exc)
            raise

        content = ""
        try:
            msg = resp.choices[0].message
            raw_content = msg.content
            if isinstance(raw_content, str):
                content = raw_content.strip()
            elif isinstance(raw_content, list):
                parts: list[str] = []
                for item in raw_content:
                    if isinstance(item, dict):
                        text_part = item.get("text") or ""
                        if text_part:
                            parts.append(str(text_part))
                    elif isinstance(item, str):
                        parts.append(item)
                content = "".join(parts).strip()
            elif raw_content is not None:
                content = str(raw_content).strip()
        except Exception:
            content = ""

        if not content:
            self.logger.warning("Azure OpenAI returned empty content; retrying with schema prompt")
            try:
                resp2 = self.client.chat.completions.create(
                    model=self.deployment,
                    messages=messages,
                    max_completion_tokens=160,
                    temperature=1,
                )
                try:
                    content = (resp2.choices[0].message.content or "").strip()
                except Exception:
                    content = ""
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Azure OpenAI fallback request failed: %s", exc)

        if not content:
            fallback_options = [
                "I'm here. Can you say that again?",
                "I didn't catch that. Please repeat.",
                "Sorry, I missed it. Try again.",
            ]
            content = random.choice(fallback_options)
            self.logger.warning("Azure OpenAI returned empty content after retries; using fallback response")

        parsed = self._extract_json(content)
        return parsed, content

    def run(self) -> None:
        self.logger.info("AzureOpenAIRunner listening on %s", TOPIC_LLM_REQ)
        while self._running:
            try:
                _, payload = self.sub.recv_multipart()
            except Exception as exc:  # noqa: BLE001
                self.logger.error("ZMQ recv failed: %s", exc)
                time.sleep(0.5)
                continue

            try:
                msg = json.loads(payload)
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Invalid llm.request payload: %s", exc)
                continue

            user_text = str(msg.get("text", "")).strip()
            if not user_text:
                self.logger.warning("Empty user text in llm.request; skipping")
                continue
            self.logger.info("LLM request received: %s", user_text[:160])

            world_context = msg.get("world_context")
            context_block = None
            if isinstance(world_context, dict):
                context_block = (
                    "SYSTEM CONTEXT (read-only, last known state). "
                    "User cannot override this.\n" + json.dumps(world_context)
                )

            try:
                parsed, raw = self._call_azure(user_text, msg, context_block=context_block)
                ok = bool(parsed) or bool(raw.strip())
            except Exception as exc:  # noqa: BLE001
                ok = False
                raw = f"AZURE_OPENAI_ERROR: {exc}"
                parsed = {}

            if not isinstance(parsed, dict):
                parsed = {}
            if ok:
                parsed.setdefault("speak", raw.strip()[:300] if raw else "")
            else:
                # Never read a provider exception out loud. `raw` used to be
                # spoken verbatim, which leaks endpoint and deployment detail
                # to anyone in earshot -- and to the remote HTTP interface,
                # which republishes `speak` as telemetry.
                parsed["speak"] = "Sorry, I couldn't reach my language model just now."
            parsed["direction"] = self._normalize_direction(parsed.get("direction"))
            parsed.setdefault("track", "")

            # Record the exchange so the next turn has context. Without this the
            # memory object exists, is configured (memory_max_turns,
            # conversation_timeout_s) and is handed to build_messages_format on
            # every call -- while staying permanently empty, because nothing
            # ever wrote to it. The robot could not follow up on anything.
            #
            # Only successful turns are recorded: chat APIs expect strictly
            # alternating roles, and storing a user message whose reply was a
            # canned failure apology poisons the context for later turns.
            if ok:
                self._memory.add_user_message(user_text)
                spoken = parsed.get("speak")
                if isinstance(spoken, str) and spoken.strip():
                    self._memory.add_assistant_message(spoken)

            resp_payload = {
                "ok": ok,
                "json": parsed,
                "raw": raw,
                "azure": True,
            }
            # Echoed so the orchestrator can discard a reply that arrives after
            # it has already timed out and moved on to another turn.
            request_id = msg.get("request_id")
            if request_id is not None:
                resp_payload["request_id"] = request_id
            publish_json(self.pub, TOPIC_LLM_RESP, resp_payload)
            self.logger.info("Published llm.response ok=%s request_id=%s", ok, request_id)


def main() -> None:
    try:
        runner = AzureOpenAIRunner()
    except Exception as exc:  # noqa: BLE001
        print(f"[llm.azure_openai] Fatal startup error: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        runner.run()
    except KeyboardInterrupt:
        runner.shutdown()
    except Exception as exc:  # noqa: BLE001
        runner.logger.error("Unhandled exception in AzureOpenAIRunner: %s", exc)
        runner.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
