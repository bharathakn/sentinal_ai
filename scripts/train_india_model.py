#!/usr/bin/env python3
"""Train the India-native behavioural model for Agent 1 (Phase 9.5).

Usage:
    PYTHONPATH=. python scripts/train_india_model.py [--data-dir DIR] [--out-dir DIR]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ml.india_behaviour_model import DEFAULT_MODEL_DIR, train  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default="dataset/processed/custom_india")
    ap.add_argument("--out-dir", default=str(DEFAULT_MODEL_DIR))
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    meta = train(Path(a.data_dir), Path(a.out_dir), seed=a.seed)
    print(json.dumps({"split": meta["split"], "metrics": meta["metrics"], "caveat": meta["caveat"]}, indent=2))
