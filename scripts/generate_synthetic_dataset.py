#!/usr/bin/env python3
"""
Sentinel AI — Custom Synthetic India Dataset Generation CLI Script

Usage:
    python scripts/generate_synthetic_dataset.py --seed 42 --num-transactions 10000 --output-dir dataset/processed/custom_india
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.synthetic_india_generator import GENERATOR_VERSION, SyntheticIndiaDatasetGenerator
from src.data.validate_synthetic_dataset import SyntheticDatasetValidator


def main():
    parser = argparse.ArgumentParser(description="Generate Sentinel AI Custom Synthetic India Dataset.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--num-transactions", type=int, default=10000, help="Total transactions to generate (default: 10000)")
    parser.add_argument("--output-dir", type=str, default="dataset/processed/custom_india", help="Target output directory")
    args = parser.parse_args()

    print("================================================================================")
    print(" Sentinel AI — Custom Synthetic India Dataset Generator")
    print("================================================================================")
    print(f"[*] Configuration: Seed={args.seed}, Transactions={args.num_transactions}")
    print(f"[*] Target Directory: {args.output_dir}")

    # Create target directory
    os.makedirs(args.output_dir, exist_ok=True)

    # 1. Initialize & Run Generator
    print("\n[1/3] Generating synthetic entities & transaction ledger...")
    generator = SyntheticIndiaDatasetGenerator(seed=args.seed, num_transactions=args.num_transactions)
    data_dict = generator.generate_all()

    # 2. Export Files
    print("[2/3] Exporting generated CSV datasets...")
    export_paths = {
        "customers": os.path.join(args.output_dir, "customers.csv"),
        "accounts": os.path.join(args.output_dir, "accounts.csv"),
        "devices": os.path.join(args.output_dir, "devices.csv"),
        "beneficiaries": os.path.join(args.output_dir, "beneficiaries.csv"),
        "transactions_features": os.path.join(args.output_dir, "transactions_features.csv"),
        "transactions_targets": os.path.join(args.output_dir, "transactions_targets.csv"),
        "graph_edges": os.path.join(args.output_dir, "graph_edges.csv")
    }

    for name, df in data_dict.items():
        path = export_paths[name]
        df.to_csv(path, index=False)
        print(f"    ✔ Exported {name:22s}: {len(df):6d} rows -> {path}")

    # Generate metadata.json
    channel_counts = data_dict["transactions_features"]["channel"].value_counts().to_dict()
    label_counts = data_dict["transactions_targets"]["risk_label"].value_counts().to_dict()
    scenario_counts = data_dict["transactions_targets"]["scenario_id"].value_counts().to_dict()

    metadata = {
        "dataset_name": "Custom Synthetic India Dataset",
        "version": GENERATOR_VERSION,
        "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        "random_seed": args.seed,
        "total_transactions": len(data_dict["transactions_features"]),
        "total_customers": len(data_dict["customers"]),
        "total_accounts": len(data_dict["accounts"]),
        "total_devices": len(data_dict["devices"]),
        "total_beneficiaries": len(data_dict["beneficiaries"]),
        "channel_breakdown": channel_counts,
        "risk_label_breakdown": label_counts,
        "scenario_breakdown": scenario_counts,
        "provenance": {
            "creator": "Sentinel AI Synthetic Generator Engine",
            "is_real_pii": False,
            "is_synthetic": True,
            "deterministic_reproducible": True
        }
    }

    metadata_path = os.path.join(args.output_dir, "dataset_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"    ✔ Exported metadata              : {metadata_path}")

    # 3. Run Validation Suite
    print("\n[3/3] Running programmatic validation checks...")
    validator = SyntheticDatasetValidator(data_dict)
    val_results = validator.validate_all()

    for check_name, status in val_results["checks"].items():
        symbol = "✔" if status == "PASSED" else "❌"
        print(f"    {symbol} Check [{check_name:35s}]: {status}")

    if val_results["passed"]:
        print("\n================================================================================")
        print(" SUCCESS: Custom Synthetic India Dataset successfully generated & saved.")
        print("================================================================================")
    else:
        print("\n================================================================================")
        print(" WARNING: Dataset generated with validation errors:")
        for err in val_results["errors"]:
            print(f"   - {err}")
        print("================================================================================")


if __name__ == "__main__":
    main()
