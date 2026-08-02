"""
Phase 1: QoS dataset preparation and offline model training.

Rebuilds the flow dataset around 4 QoS classes (Delay-Sensitive,
Video-Streaming, Bulk-Download, Web-Browsing), extracts SPLT features from
strictly the first N_PACKETS packets of each flow, trains RandomForest and
LightGBM classifiers, and pickles the better performer for the Phase 2
router sniffer.

Usage:
    python phase1_train.py [--data-path PATH] [--n-packets 10]
                            [--models-dir DIR] [--cv-splits 5]

If --data-path does not point at a real Parquet file (e.g. it's still an
unfetched Git LFS pointer), the script fetches it from the source repo via
the same sparse git-checkout the tutorial notebooks use.
"""

import argparse
import json
import pickle
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.qos_mapping import QOS_CLASSES, map_to_qos_class
from common.splt_features import build_feature_matrix, feature_names

REPO_URL = "https://github.com/FlowFrontiers/ml-flow-class-tutorial.git"
REPO_RELATIVE_DATA_PATH = "02-app-classification/data/data.parquet"

# Matches the cleaning pipeline in 02-app-classification/02a-data-preparation.ipynb
MIN_APPLICATION_CONFIDENCE = 6  # nDPI NDPI_CONFIDENCE_DPI (full DPI match, not port/heuristic guess)


def is_valid_parquet(path: Path) -> bool:
    if not path.exists():
        return False
    with open(path, "rb") as f:
        return f.read(4) == b"PAR1"


def ensure_dataset(path: Path) -> Path:
    if is_valid_parquet(path):
        return path

    print(f"[data] {path} is missing or an unfetched Git LFS pointer -- fetching via sparse checkout...")
    tmp_clone = path.parent / ".phase1_fetch_tmp"
    if tmp_clone.exists():
        shutil.rmtree(tmp_clone)

    try:
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--sparse", "-n", REPO_URL, str(tmp_clone)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_clone), "sparse-checkout", "set", REPO_RELATIVE_DATA_PATH],
            check=True,
        )
        subprocess.run(["git", "-C", str(tmp_clone), "checkout"], check=True)
        fetched = tmp_clone / REPO_RELATIVE_DATA_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fetched, path)
    finally:
        if tmp_clone.exists():
            shutil.rmtree(tmp_clone)

    if not is_valid_parquet(path):
        raise RuntimeError(
            f"Could not fetch a valid data.parquet at {path}. "
            "Fetch it manually (e.g. `git lfs pull`) and re-run."
        )
    return path


def load_and_clean(data_path: Path, min_packets: int) -> pd.DataFrame:
    df = pd.read_parquet(data_path)
    print(f"[data] loaded {len(df):,} raw flows, {df.shape[1]} columns")

    clean = df[df["application_is_guessed"] == 0].copy()
    clean = clean[clean["application_confidence"] == MIN_APPLICATION_CONFIDENCE].copy()
    clean = clean[clean["application_name"] != "Unknown"].copy()
    clean = clean[clean["bidirectional_packets"] >= min_packets].copy()
    print(f"[data] {len(clean):,} flows remain after DPI-confidence and >= {min_packets}-packet filtering")
    return clean


def map_labels(df: pd.DataFrame) -> pd.DataFrame:
    unmapped_categories = set()
    df["qos_class"] = [
        map_to_qos_class(name, category, unmapped_categories)
        for name, category in zip(df["application_name"], df["application_category_name"])
    ]
    if unmapped_categories:
        print(
            "[labels] WARNING: application_category_name values with no explicit "
            f"CATEGORY_MAP entry (defaulted to Web-Browsing): {sorted(unmapped_categories)}"
        )
    print("[labels] QoS class distribution:")
    counts = df["qos_class"].value_counts()
    for cls, n in counts.items():
        print(f"    {cls:<18} {n:>8,}  ({100 * n / len(df):5.1f}%)")
    return df


def train_and_select(X, y, groups, n_splits, random_state=42):
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    print(
        f"[split] {len(train_idx):,} train / {len(test_idx):,} test flows "
        f"(grouped by client IP -- {len(set(groups[train_idx])):,} / {len(set(groups[test_idx])):,} distinct clients)"
    )

    candidates = {
        # max_depth/min_samples_leaf are bounded deliberately: unbounded trees on
        # ~350K rows produce a >1GB pickle, impractical for a router-deployed
        # sniffer. This config trades ~0.015 macro F1 for a ~240MB model.
        # n_jobs is capped (not -1) to bound peak memory during tree construction.
        "RandomForest": RandomForestClassifier(
            n_estimators=100,
            max_depth=22,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=2,
        ),
        "LightGBM": lgb.LGBMClassifier(
            n_estimators=200, class_weight="balanced", random_state=random_state, n_jobs=2, verbosity=-1
        ),
    }

    results = {}
    for name, model in candidates.items():
        print(f"[train] fitting {name}...")
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        macro_f1 = f1_score(y_test, y_pred, average="macro")
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        cm = confusion_matrix(y_test, y_pred).tolist()
        print(f"[eval] {name}: macro F1 = {macro_f1:.4f}")
        results[name] = {
            "model": model,
            "macro_f1": macro_f1,
            "classification_report": report,
            "confusion_matrix": cm,
        }

    best_name = max(results, key=lambda k: results[k]["macro_f1"])
    print(f"[select] best model: {best_name} (macro F1 = {results[best_name]['macro_f1']:.4f})")
    return best_name, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / REPO_RELATIVE_DATA_PATH,
    )
    parser.add_argument("--n-packets", type=int, default=10)
    parser.add_argument("--models-dir", type=Path, default=Path(__file__).resolve().parent / "models")
    parser.add_argument("--cv-splits", type=int, default=5)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    data_path = ensure_dataset(args.data_path)
    df = load_and_clean(data_path, min_packets=args.n_packets)
    df = map_labels(df)

    print(f"[features] extracting first {args.n_packets}-packet SPLT features...")
    X = build_feature_matrix(df, n_packets=args.n_packets)
    label_encoder = LabelEncoder().fit(QOS_CLASSES)
    y = label_encoder.transform(df["qos_class"].to_numpy())
    groups = df["src_ip"].to_numpy()

    best_name, results = train_and_select(X, y, groups, n_splits=args.cv_splits, random_state=args.random_state)
    best = results[best_name]

    args.models_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.models_dir / "qos_classifier.pkl"
    metrics_path = args.models_dir / "phase1_metrics.json"

    bundle = {
        "model": best["model"],
        "model_type": best_name,
        "label_encoder": label_encoder,
        "qos_classes": QOS_CLASSES,
        "feature_names": feature_names(args.n_packets),
        "n_packets": args.n_packets,
        "sklearn_version": sklearn.__version__,
        "lightgbm_version": lgb.__version__,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(model_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"[save] model bundle -> {model_path}")

    metrics = {
        "n_flows_total": int(len(df)),
        "n_packets": args.n_packets,
        "qos_class_distribution": df["qos_class"].value_counts().to_dict(),
        "models": {
            name: {
                "macro_f1": res["macro_f1"],
                "classification_report": res["classification_report"],
                "confusion_matrix": res["confusion_matrix"],
            }
            for name, res in results.items()
        },
        "selected_model": best_name,
    }
    if hasattr(best["model"], "feature_importances_"):
        metrics["feature_importances"] = dict(
            zip(feature_names(args.n_packets), best["model"].feature_importances_.tolist())
        )
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[save] metrics -> {metrics_path}")


if __name__ == "__main__":
    main()
