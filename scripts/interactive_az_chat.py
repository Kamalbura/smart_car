#!/usr/bin/env python3
"""Interactive Azure OpenAI chat using the main system prompt.

Loads AZURE_OPENAI_* from .env and starts a REPL.
Type 'exit' or 'quit' to stop.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Dict

from openai import AzureOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm.conversation_memory import ConversationMemory


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


def _build_messages(memory: ConversationMemory, user_text: str) -> List[Dict[str, str]]:
    return memory.build_messages_format(user_text)


def main() -> int:
    _load_dotenv()

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview").strip()

    if not endpoint or not deployment or not api_key:
        print("Missing AZURE_OPENAI_ENDPOINT/DEPLOYMENT/API_KEY", file=sys.stderr)
        return 2

    client = AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=api_key,
    )

    memory = ConversationMemory()

    print("Interactive chat ready. Type 'exit' to quit.")
    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break

        memory.add_user_message(user_text)
        messages = _build_messages(memory, user_text)
        resp = client.chat.completions.create(
            model=deployment,
            messages=messages,
            max_completion_tokens=512,
        )
        reply = resp.choices[0].message.content or ""
        print(f"robo> {reply}")
        memory.add_assistant_message(reply)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
