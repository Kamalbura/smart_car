"""Minimal wrapper around YOLODetector to support streaming inference."""
from __future__ import annotations

from typing import Iterator, List

import numpy as np

from .detector import Detection, VisionConfig, YOLODetector


class VisionPipeline:
    def __init__(self, config: VisionConfig) -> None:
        self.config = config
        self.detector = YOLODetector(config)

    def bootstrap(self) -> None:
        self.detector.load()

    def run(self, stream: Iterator[np.ndarray]) -> Iterator[List[Detection]]:
        for frame in stream:
            yield self.detector.detect(frame)

    def infer_once(self, frame: np.ndarray) -> List[Detection]:
        return self.detector.detect(frame)
