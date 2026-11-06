"""Imitation-learning entry point (skeleton): loads recordings, model training TBD."""

from __future__ import annotations

import argparse

from ai_kart_wii.config import AppConfig
from ai_kart_wii.training.dataset import RecordedRun, list_runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the imitation agent from recorded runs")
    parser.add_argument("--runs", default=None, help="recorded_runs folder (default from config)")
    args = parser.parse_args(argv)
    runs_dir = args.runs or AppConfig().paths.recorded_runs
    runs = list_runs(runs_dir)
    total = sum(sum(1 for _ in RecordedRun(r).samples()) for r in runs)
    print(f"{len(runs)} runs, {total} samples in {runs_dir}")
    raise NotImplementedError("Model + training loop not implemented yet (needs the `ml` extra, torch).")


if __name__ == "__main__":
    raise SystemExit(main())
