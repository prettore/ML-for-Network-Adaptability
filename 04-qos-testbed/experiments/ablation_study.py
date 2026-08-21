"""
Systematic ablation study for two design choices phase1_train.py currently
hardcodes: the Random Forest hyperparameters (n_estimators/max_depth/
min_samples_leaf) and the SPLT feature window (n_packets=10). Both were
originally chosen from a small number of manual trials; this script runs a
principled sweep to either justify or replace them.

Design (one-factor-at-a-time, not full grid search, for tractable compute
on a single machine -- see the paper's Methodology section for why this is
an acceptable substitute for exhaustive grid/random search here):

  Experiment A -- SPLT window length (n_packets in {5, 8, 10, 12, 15, 20}),
  RF hyperparameters held at the current default. Requires a fresh
  feature matrix and train/test split per value (both depend on n_packets),
  but the base DPI-confidence cleaning is done once and reused.

  Experiment B -- RF hyperparameters, n_packets held at 10 (the value
  Experiment A is expected to support). Three one-factor sweeps around the
  current default (n_estimators=100, max_depth=22, min_samples_leaf=3):
  max_depth, min_samples_leaf, n_estimators, each varied independently.

Every fitted model is scored, sized, and discarded (del + gc.collect())
before the next one is trained, so only one model is ever resident in
memory at a time. Size is measured by pickling to a temp file and reading
its byte count back, not len(pickle.dumps(model)) -- the latter briefly
holds the entire serialized model as a second in-memory copy alongside
the live model object, which is exactly what triggered a MemoryError
partway through the n_estimators sweep (300-tree models here run ~700MB)
during the actual run this script's results come from.

Usage:
    python3 ablation_study.py [--data-path PATH] [--out results.json]
"""

import argparse
import gc
import json
import os
import pickle
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.qos_mapping import QOS_CLASSES, map_to_qos_class
from common.splt_features import build_feature_matrix

MIN_APPLICATION_CONFIDENCE = 6
RANDOM_STATE = 42
CV_SPLITS = 5

# The configuration phase1_train.py currently deploys -- the center point
# every sweep below varies away from, one factor at a time.
DEFAULT_N_PACKETS = 10
DEFAULT_RF = {"n_estimators": 100, "max_depth": 22, "min_samples_leaf": 3}

N_PACKETS_GRID = [5, 8, 10, 12, 15, 20]
MAX_DEPTH_GRID = [8, 12, 16, 20, 26, 30]  # 22 (default) covered by Experiment A's n_packets=10 run
MIN_LEAF_GRID = [1, 2, 5, 10, 20]  # 3 (default) covered likewise
N_ESTIMATORS_GRID = [25, 50, 150, 200, 300]  # 100 (default) covered likewise


def load_base_cleaned(data_path):
    df = pd.read_parquet(data_path)
    print(f"[data] loaded {len(df):,} raw flows")
    df = df[df["application_is_guessed"] == 0]
    df = df[df["application_confidence"] == MIN_APPLICATION_CONFIDENCE]
    df = df[df["application_name"] != "Unknown"].copy()
    print(f"[data] {len(df):,} flows after DPI-confidence filtering (packet-count filter applied per n_packets value)")
    return df


def prepare(df_base, n_packets):
    df = df_base[df_base["bidirectional_packets"] >= n_packets].copy()
    unmapped = set()
    df["qos_class"] = [
        map_to_qos_class(name, cat, unmapped) for name, cat in zip(df["application_name"], df["application_category_name"])
    ]
    X = build_feature_matrix(df, n_packets=n_packets)
    label_encoder = LabelEncoder().fit(QOS_CLASSES)
    y = label_encoder.transform(df["qos_class"].to_numpy())
    groups = df["src_ip"].to_numpy()
    splitter = StratifiedGroupKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    return {
        "n_flows_total": len(df),
        "class_distribution": df["qos_class"].value_counts().to_dict(),
        "X_train": X[train_idx],
        "X_test": X[test_idx],
        "y_train": y[train_idx],
        "y_test": y[test_idx],
    }


def pickle_size_mb(model):
    """Size the pickled model by streaming to a temp file rather than
    len(pickle.dumps(model)), which briefly holds a full second copy of a
    (potentially 700MB+) model in RAM just to measure it."""
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        path = tf.name
    try:
        with open(path, "wb") as f:
            pickle.dump(model, f)
        return os.path.getsize(path) / 1e6
    finally:
        os.remove(path)


def evaluate_rf(data, **rf_kwargs):
    model = RandomForestClassifier(class_weight="balanced", random_state=RANDOM_STATE, n_jobs=2, **rf_kwargs)
    t0 = time.time()
    model.fit(data["X_train"], data["y_train"])
    train_seconds = time.time() - t0
    y_pred = model.predict(data["X_test"])
    macro_f1 = f1_score(data["y_test"], y_pred, average="macro")
    report = classification_report(data["y_test"], y_pred, output_dict=True, zero_division=0)
    pickle_mb = pickle_size_mb(model)
    result = {
        "params": rf_kwargs,
        "macro_f1": macro_f1,
        "accuracy": report["accuracy"],
        "per_class_f1": {k: v["f1-score"] for k, v in report.items() if k.isdigit()},
        "pickle_mb": pickle_mb,
        "train_seconds": train_seconds,
    }
    del model, y_pred
    gc.collect()
    print(
        f"    -> macro_f1={macro_f1:.4f} accuracy={report['accuracy']:.4f} "
        f"size={pickle_mb:.1f}MB train_time={train_seconds:.1f}s"
    )
    return result


def run_experiment_a(df_base):
    print("\n[experiment A] SPLT window length (n_packets) sweep")
    results = {}
    packets_data_for_b = None
    for n_packets in N_PACKETS_GRID:
        print(f"  n_packets={n_packets}: building features + splitting...")
        data = prepare(df_base, n_packets)
        print(
            f"    {data['n_flows_total']:,} flows retained "
            f"({100 * data['n_flows_total'] / len(df_base):.1f}% of DPI-confident flows)"
        )
        res = evaluate_rf(data, **DEFAULT_RF)
        res["n_flows_total"] = data["n_flows_total"]
        res["pct_flows_retained"] = 100 * data["n_flows_total"] / len(df_base)
        res["class_distribution"] = data["class_distribution"]
        results[str(n_packets)] = res
        if n_packets == DEFAULT_N_PACKETS:
            packets_data_for_b = data  # reuse for Experiment B, avoid rebuilding
        else:
            del data
        gc.collect()
    return results, packets_data_for_b


def run_experiment_b(data_n10):
    print("\n[experiment B] Random Forest hyperparameter sweeps (n_packets=10)")
    results = {"baseline": None, "max_depth": {}, "min_samples_leaf": {}, "n_estimators": {}}

    print(f"  baseline {DEFAULT_RF}:")
    results["baseline"] = evaluate_rf(data_n10, **DEFAULT_RF)

    print("  max_depth sweep (n_estimators=100, min_samples_leaf=3):")
    for depth in MAX_DEPTH_GRID:
        print(f"    max_depth={depth}:")
        cfg = {**DEFAULT_RF, "max_depth": depth}
        results["max_depth"][str(depth)] = evaluate_rf(data_n10, **cfg)

    print("  min_samples_leaf sweep (n_estimators=100, max_depth=22):")
    for leaf in MIN_LEAF_GRID:
        print(f"    min_samples_leaf={leaf}:")
        cfg = {**DEFAULT_RF, "min_samples_leaf": leaf}
        results["min_samples_leaf"][str(leaf)] = evaluate_rf(data_n10, **cfg)

    print("  n_estimators sweep (max_depth=22, min_samples_leaf=3):")
    for n_est in N_ESTIMATORS_GRID:
        print(f"    n_estimators={n_est}:")
        cfg = {**DEFAULT_RF, "n_estimators": n_est}
        results["n_estimators"][str(n_est)] = evaluate_rf(data_n10, **cfg)

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "02-app-classification" / "data" / "data.parquet",
    )
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "ablation_results.json")
    args = parser.parse_args()

    df_base = load_base_cleaned(args.data_path)

    exp_a, data_n10 = run_experiment_a(df_base)
    del df_base
    gc.collect()

    exp_b = run_experiment_b(data_n10)

    out = {
        "config": {
            "default_n_packets": DEFAULT_N_PACKETS,
            "default_rf": DEFAULT_RF,
            "n_packets_grid": N_PACKETS_GRID,
            "max_depth_grid": MAX_DEPTH_GRID,
            "min_samples_leaf_grid": MIN_LEAF_GRID,
            "n_estimators_grid": N_ESTIMATORS_GRID,
            "cv_splits": CV_SPLITS,
            "random_state": RANDOM_STATE,
        },
        "experiment_a_n_packets": exp_a,
        "experiment_b_rf_hyperparams": exp_b,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[save] full results -> {args.out}")


if __name__ == "__main__":
    main()
