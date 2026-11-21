#!/usr/bin/env python3
"""Build the runtime artifacts a deployment needs (idempotent).

The India synthetic dataset and the India behaviour model are gitignored but
fully reproducible: generator seed 42 and training seed 42 produce
byte-identical CSVs and model files. A hosted build (e.g. a Render build
command) runs this instead of shipping the files:

    python scripts/build_artifacts.py

Steps (each skipped if its output already exists, unless --force):
  1. generate dataset/processed/custom_india/   (~2 s)
  2. train   models/india_behaviour/v1/         (~3 s)

The Neo4j graph is NOT loaded here: graph loading is a one-time operation
against the target database (scripts/load_india_sample_graph.py).
IEEE-CIS models are not built (they need the 1.8 GB raw dataset); set
SENTINEL_REQUIRE_IEEE_MODELS=false where they are absent.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "dataset/processed/custom_india"
MODEL_DIR = ROOT / "models/india_behaviour/v1"
REQUIRED_DATA = ("customers.csv", "accounts.csv", "devices.csv", "beneficiaries.csv",
                 "transactions_features.csv", "graph_edges.csv")
REQUIRED_MODEL = ("xgb_model.joblib", "if_model.joblib", "metadata.json")


def _complete(d: Path, names: tuple[str, ...]) -> bool:
    return all((d / n).exists() for n in names)


def _run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="Rebuild even if outputs exist")
    a = ap.parse_args()

    if a.force or not _complete(DATA_DIR, REQUIRED_DATA):
        _run("scripts/generate_synthetic_dataset.py", "--output-dir", str(DATA_DIR))
    else:
        print(f"dataset present: {DATA_DIR.relative_to(ROOT)}")

    if a.force or not _complete(MODEL_DIR, REQUIRED_MODEL):
        _run("scripts/train_india_model.py", "--data-dir", str(DATA_DIR), "--out-dir", str(MODEL_DIR))
    else:
        print(f"model present: {MODEL_DIR.relative_to(ROOT)}")

    ok = _complete(DATA_DIR, REQUIRED_DATA) and _complete(MODEL_DIR, REQUIRED_MODEL)
    print("artifacts ready" if ok else "artifact build INCOMPLETE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
