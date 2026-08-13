#!/usr/bin/env python3
"""One-shot Azure OpenAI Responses API test for GPT-5 mini deployment.

Usage:
  python tools/test_azure_openai_gpt5_mini.py --prompt "Robo, scan surroundings"

Reads env vars:
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_DEPLOYMENT
  AZURE_OPENAI_API_VERSION (optional)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from openai import OpenAI


def _extract_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        if raw[0] == "{" and raw[-1] == "}":
            return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except Exception:
            return {}
    return {}


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"").strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Azure OpenAI GPT-5 mini test")
    parser.add_argument(
        "--prompt",
        default="Robo, scan surroundings and report anything ahead.",
        help="User prompt to send",
    )
    parser.add_argument(
        "--api",
        choices=["responses", "chat"],
        default="chat",
        help="API to use for the test",
    )
    parser.add_argument(
        "--input_mode",
        choices=["messages", "text"],
        default="text",
        help="Input mode for Responses API",
    )
    parser.add_argument(
        "--max_tokens",
        type=int,
        default=160,
        help="Max output tokens",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature (omit if model doesn't support)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Request JSON-only output via response_format",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print full response object for debugging",
    )
    args = parser.parse_args()

    _load_dotenv()

    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-03-01-preview").strip()

    if not api_key:
        print("Missing AZURE_OPENAI_API_KEY", file=sys.stderr)
        return 2
    if not endpoint:
        print("Missing AZURE_OPENAI_ENDPOINT", file=sys.stderr)
        return 2
    if not deployment:
        print("Missing AZURE_OPENAI_DEPLOYMENT", file=sys.stderr)
        return 2

    # Normalize base_url for Azure OpenAI Foundry endpoints
    base_url = endpoint
    if "/openai/responses" in base_url:
        base_url = base_url.split("/openai/responses", 1)[0]
    if "/openai/" not in base_url:
        base_url = base_url.rstrip("/") + "/openai/v1/"
    if not base_url.endswith("/"):
        base_url += "/"

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    system_prompt = (
        "You are ROBO, a smart assistant for a robotic car. "
        "Reply with JSON only: {\"speak\": string, \"direction\": "
        "'forward'|'backward'|'left'|'right'|'stop', \"track\": string}. "
        "If no movement, use direction 'stop' and empty track."
    )

    if args.api == "responses":
        if args.input_mode == "messages":
            input_payload = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": args.prompt},
            ]
        else:
            input_payload = args.prompt

        request_args = {
            "model": deployment,
            "input": input_payload,
            "max_output_tokens": args.max_tokens,
        }
        if args.temperature is not None:
            request_args["temperature"] = args.temperature

        resp = client.responses.create(**request_args)

        raw_text = getattr(resp, "output_text", "") or ""
        if not raw_text:
            outputs = getattr(resp, "output", None) or []
            collected = []
            for item in outputs:
                contents = getattr(item, "content", None) or []
                for content in contents:
                    text = getattr(content, "text", None)
                    if text:
                        collected.append(text)
            raw_text = "\n".join(collected).strip()
    else:
        chat_args = {
            "model": deployment,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": args.prompt},
            ],
            "max_completion_tokens": args.max_tokens,
        }
        if args.temperature is not None:
            chat_args["temperature"] = args.temperature
        if args.json:
            chat_args["response_format"] = {"type": "json_object"}

        resp = client.chat.completions.create(**chat_args)
        choice = resp.choices[0] if resp.choices else None
        raw_text = choice.message.content if choice and choice.message else ""

    parsed = _extract_json(raw_text)

    print("\n=== RESPONSE META ===")
    print(f"api={args.api}")
    print(f"id={getattr(resp, 'id', '')}")
    print(f"model={getattr(resp, 'model', '')}")
    usage = getattr(resp, "usage", None)
    if usage:
        print(f"usage={usage}")
    if args.debug:
        print("\n=== RESPONSE DEBUG ===")
        try:
            dump = resp.model_dump()
        except Exception:
            dump = str(resp)
        print(dump)

    print("\n=== RAW OUTPUT ===")
    print(raw_text)
    print("\n=== PARSED JSON ===")
    print(json.dumps(parsed, indent=2) if parsed else "(no JSON found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
