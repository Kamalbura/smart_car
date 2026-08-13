"""Developer tooling entrypoint.

Updated to use new typed configuration loader (`ConfigLoader`) and
`OfflineAssistant` wrapper for legacy bootstrap tests.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config_loader import ConfigLoader
from src.core.orchestrator import OfflineAssistant, OrchestratorConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline assistant CLI")
    parser.add_argument("--config", default="config/system.yaml", help="Path to system config")
    args = parser.parse_args()

    loader = ConfigLoader(Path(args.config))
    core_cfg = loader.load()
    orch_cfg = OrchestratorConfig(
        stt=core_cfg.stt,
        tts=core_cfg.tts,
        llm=core_cfg.llm,
        vision=core_cfg.vision,
        display=core_cfg.display,  # type: ignore[arg-type]
    )
    orchestrator = OfflineAssistant(orch_cfg)
    try:
        orchestrator.bootstrap()
    except FileNotFoundError as exc:
        print(f"Bootstrap incomplete: {exc}")
    print("Assistant ready. Implement event loop to start conversations.")


if __name__ == "__main__":
    main()
