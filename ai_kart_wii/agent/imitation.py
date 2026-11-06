"""Screenshot-only imitation agent (skeleton).

Plan: a small CNN takes the last K preprocessed frames (+ optional scalar features such
as speed) and predicts (steer, accelerate, brake, drift). Training data comes from
recorded human runs (recording/), see training/. Until a model exists this agent falls
back to a fixed "accelerate straight" action so the pipeline can be exercised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from ai_kart_wii.control.actions import DrivingAction
from ai_kart_wii.env.observation import Observation, preprocess_frame


class PolicyModel(Protocol):
    def predict(self, frames: np.ndarray) -> DrivingAction:
        """frames: (K, H, W, C) float32 in [0, 1]."""


class ImitationAgent:
    def __init__(self, model: PolicyModel | None = None, frame_stack: int = 4, size: tuple[int, int] = (160, 120)) -> None:
        self.model = model
        self.frame_stack = frame_stack
        self.size = size
        self._frames: list[np.ndarray] = []

    @classmethod
    def from_file(cls, path: str | Path) -> "ImitationAgent":
        raise NotImplementedError("Model loading arrives with the training step (needs the `ml` extra).")

    def reset(self) -> None:
        self._frames.clear()

    def act(self, observation: Observation) -> DrivingAction:
        if observation.frame is None:
            return DrivingAction()
        self._frames.append(preprocess_frame(observation.frame.image, self.size))
        self._frames = self._frames[-self.frame_stack:]
        if self.model is None or len(self._frames) < self.frame_stack:
            return DrivingAction(steer=0.0, accelerate=True)
        return self.model.predict(np.stack(self._frames))
