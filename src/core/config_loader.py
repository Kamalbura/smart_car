"""Utility helpers to load YAML config with environment expansion.

Extended with a lightweight typed configuration loader (`ConfigLoader`) used by
developer tooling and legacy tests. The existing `load_config` function is
retained for modules expecting a plain dict.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from dataclasses import dataclass
from enum import Enum

try:  # Local imports deferred to avoid circulars in test bootstrap
    from src.vision.detector import VisionConfig  # type: ignore
    from pathlib import Path as _PathAlias  # for type hints only
except Exception:  # pragma: no cover - exercised wherever cv2/onnxruntime are absent
    # The point of this fallback is that config loading still works on a host
    # without the vision dependencies. Aliasing to `object` did the opposite:
    # the import succeeded and the first VisionConfig(...) call then died with
    # "object() takes no arguments". A stand-in with the same fields keeps the
    # promise.
    @dataclass(slots=True)
    class VisionConfig:  # type: ignore[no-redef]
        model_path: Path = Path("missing")
        input_size: tuple = (640, 640)
        confidence: float = 0.25
        iou: float = 0.45

    _PathAlias = Path

# Placeholder dataclasses for legacy typed config loader (TTSConfig, LlamaConfig deleted)
@dataclass(slots=True)
class TTSConfig:
    voice: str = "en-us-amy-medium"
    model_path: Path = Path("missing")
    sample_rate: int = 22050
    noise_scale: float = 0.6
    length_scale: float = 1.0


@dataclass(slots=True)
class LlamaConfig:
    model_path: Path = Path("missing")
    context_tokens: int = 2048
    gpu_layers: int = 0
    threads: int = 4

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - ensures clearer error at runtime
    yaml = None

ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def load_config(path: Path) -> Dict[str, Any]:
    """Load YAML/JSON config expanding ${PROJECT_ROOT} and ${ENV:VAR}."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    project_root = path.resolve().parent.parent
    _load_dotenv(project_root / ".env")

    if path.suffix not in {".yaml", ".yml"}:
        raise ValueError("Unsupported config format; only YAML supported")
    if yaml is None:
        raise ModuleNotFoundError("PyYAML is required to read YAML configs; install pyyaml")

    data = yaml.safe_load(path.read_text()) or {}
    return _expand(data, project_root)


def _load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        os.environ.setdefault(key, value)


def _expand(value: Any, project_root: Path) -> Any:
    if isinstance(value, dict):
        return {k: _expand(v, project_root) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, project_root) for v in value]
    if isinstance(value, str):
        return _expand_string(value, project_root)
    return value


def _expand_string(value: str, project_root: Path) -> str:
    def replacer(match: re.Match[str]) -> str:
        token = match.group(1)
        if ":-" in token and not token.startswith("ENV:"):
            name, default = token.split(":-", 1)
            return os.environ.get(name, default)
        if token == "PROJECT_ROOT":
            return str(project_root)
        if token.startswith("ENV:"):
            env_key = token.split(":", 1)[1]
            return os.environ.get(env_key, "")
        return os.environ.get(token, match.group(0))

    value = value.replace("${PROJECT_ROOT}", str(project_root))
    value = ENV_PATTERN.sub(replacer, value)
    value = os.path.expandvars(value)
    value = os.path.expanduser(value)
    return value


# ---------------------------------------------------------------------------
# Typed configuration layer used by legacy tests / CLI tooling.
# ---------------------------------------------------------------------------

class STTBackend(Enum):
    WHISPER_CPP = "whisper_cpp"
    OTHER = "other"


@dataclass(slots=True)
class RecognizerConfig:
    backend: STTBackend
    model_path: Path


@dataclass(slots=True)
class CoreConfig:
    stt: RecognizerConfig
    tts: TTSConfig  # type: ignore[valid-type]
    llm: LlamaConfig  # type: ignore[valid-type]
    vision: VisionConfig  # type: ignore[valid-type]
    display: Dict[str, Any]


class ConfigLoader:
    """Legacy helper producing typed config objects for tests.

    Only parses a subset of fields required by the existing tests. Additional
    keys can be added with backward-compatible defaults as the implementation
    grows.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> CoreConfig:
        raw = load_config(self.path)
        # STT
        stt_raw = raw.get("stt", {})
        backend = STTBackend(stt_raw.get("backend", "whisper_cpp"))
        stt_cfg = RecognizerConfig(backend=backend, model_path=Path(stt_raw.get("model_path", "missing")))
        # TTS
        tts_raw = raw.get("tts", {})
        tts_cfg = TTSConfig(  # type: ignore[call-arg]
            voice=tts_raw.get("voice", "demo"),
            model_path=Path(tts_raw.get("model_path", "missing")),
            sample_rate=int(tts_raw.get("sample_rate", 22050)),
            noise_scale=float(tts_raw.get("noise_scale", 0.6)),
            length_scale=float(tts_raw.get("length_scale", 1.0)),
        )
        # LLM
        llm_raw = raw.get("llm", {})
        llm_cfg = LlamaConfig(  # type: ignore[call-arg]
            model_path=Path(llm_raw.get("model_path", "missing")),
            context_tokens=int(llm_raw.get("context_tokens", 2048)),
            gpu_layers=int(llm_raw.get("gpu_layers", 0)),
            threads=int(llm_raw.get("threads", 4)),
        )
        # Vision
        vis_raw = raw.get("vision", {})
        vision_cfg = VisionConfig(  # type: ignore[call-arg]
            model_path=Path(vis_raw.get("model_path", vis_raw.get("model_path_onnx", "missing"))),
            input_size=tuple(vis_raw.get("input_size", (640, 640))),
            confidence=float(vis_raw.get("confidence", 0.25)),
            iou=float(vis_raw.get("iou", 0.45)),
        )
        display_cfg = raw.get("display", {})
        return CoreConfig(stt=stt_cfg, tts=tts_cfg, llm=llm_cfg, vision=vision_cfg, display=display_cfg)
