"""
Processing-latency sweep across SPLT feature-window lengths.

ablation_study.py's Experiment A already shows how macro F1, accuracy, and
model size change with n_packets (Table 4 of the paper). It does not touch
latency, and the paper's only latency figure (Table 7) was measured once,
at the deployed n_packets=10, from 8 real live-sniffer events during the
pilot run. This script asks the complementary question directly: does
processing latency itself change as the window gets shorter or longer?

For each n_packets in the same grid ablation_study.py uses, we rebuild the
dataset and retrain the deployed-hyperparameter Random Forest exactly as
Experiment A does (same cleaning, same StratifiedGroupKFold split, same
random_state, so the model here is the same one Table 4's numbers describe),
then benchmark two costs on a random sample of held-out test flows, timed
one flow at a time (never batched) to match how the live sniffer actually
calls this code -- one flow, one classification event:

  - feature extraction: common/splt_features.extract_splt_features on a
    single flow's raw SPLT columns, the exact function the live sniffer
    (router/flow_tracker.py) and the offline trainer both import, so there
    is no separate "benchmark version" of this code path.
  - model inference: model.predict() on that single flow's feature vector.

tc/iptables enforcement latency (Table 7's third stage, ~4.8ms) is not
re-measured here: it is a fixed per-flow kernel-rule-installation cost that
does not depend on n_packets or the feature vector at all, so re-timing it
per sweep point would not add information.

Usage:
    python3 latency_study.py [--data-path PATH] [--out results.json] [--n-samples 300]
"""

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ablation_study import DEFAULT_RF, N_PACKETS_GRID, RANDOM_STATE, CV_SPLITS, load_base_cleaned
from common.qos_mapping import QOS_CLASSES, map_to_qos_class
from common.splt_features import build_feature_matrix, extract_splt_features

N_SAMPLES_DEFAULT = 300
N_WARMUP = 10  # untimed calls first, to avoid a cold-start outlier skewing the mean


def prepare_with_df(df_base, n_packets):
    """Same filtering/labeling/split as ablation_study.prepare(), but also
    returns the filtered dataframe and the test-set row positions, so we can
    go back to raw SPLT columns for single-flow feature-extraction timing."""
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
    return df, X, y, train_idx, test_idx


def benchmark_latency(df, X, test_idx, model, n_packets, n_samples, rng):
    sample_pos = rng.choice(test_idx, size=min(n_samples, len(test_idx)), replace=False)
    df_test = df.iloc[sample_pos]

    # Warm up both code paths before timing (first-call overhead, e.g. RF
    # thread-pool spin-up, should not count against every sweep point
    # unevenly).
    for i in range(min(N_WARMUP, len(sample_pos))):
        pos = sample_pos[i]
        row = df_test.iloc[i]
        extract_splt_features(row["splt_ps"], row["splt_direction"], row["splt_piat_ms"], n_packets=n_packets)
        model.predict(X[pos].reshape(1, -1))

    feature_ms, inference_ms = [], []
    for i in range(len(sample_pos)):
        pos = sample_pos[i]
        row = df_test.iloc[i]

        t0 = time.perf_counter()
        extract_splt_features(row["splt_ps"], row["splt_direction"], row["splt_piat_ms"], n_packets=n_packets)
        feature_ms.append((time.perf_counter() - t0) * 1000)

        vec = X[pos].reshape(1, -1)
        t0 = time.perf_counter()
        model.predict(vec)
        inference_ms.append((time.perf_counter() - t0) * 1000)

    feature_ms = np.array(feature_ms)
    inference_ms = np.array(inference_ms)
    total_ms = feature_ms + inference_ms
    return {
        "n_samples": len(sample_pos),
        "feature_extraction_ms": {"mean": float(feature_ms.mean()), "median": float(np.median(feature_ms))},
        "model_inference_ms": {"mean": float(inference_ms.mean()), "median": float(np.median(inference_ms))},
        "total_ms": {"mean": float(total_ms.mean()), "median": float(np.median(total_ms))},
    }


def run(df_base, n_samples):
    rng = np.random.default_rng(RANDOM_STATE)
    results = {}
    for n_packets in N_PACKETS_GRID:
        print(f"\n[n_packets={n_packets}] building features + retraining deployed-hyperparameter RF...")
        df, X, y, train_idx, test_idx = prepare_with_df(df_base, n_packets)
        model = RandomForestClassifier(class_weight="balanced", random_state=RANDOM_STATE, n_jobs=2, **DEFAULT_RF)
        model.fit(X[train_idx], y[train_idx])

        lat = benchmark_latency(df, X, test_idx, model, n_packets, n_samples, rng)
        results[str(n_packets)] = lat
        print(
            f"    feature={lat['feature_extraction_ms']['mean']:.4f}ms "
            f"inference={lat['model_inference_ms']['mean']:.4f}ms "
            f"total={lat['total_ms']['mean']:.4f}ms  (mean over {lat['n_samples']} single-flow calls)"
        )

        del df, X, y, train_idx, test_idx, model
        gc.collect()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-path", type=Path,
        default=Path(__file__).resolve().parents[2] / "02-app-classification" / "data" / "data.parquet",
    )
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "latency_results.json")
    parser.add_argument("--n-samples", type=int, default=N_SAMPLES_DEFAULT)
    args = parser.parse_args()

    df_base = load_base_cleaned(args.data_path)
    results = run(df_base, args.n_samples)

    out = {
        "config": {
            "n_packets_grid": N_PACKETS_GRID,
            "deployed_rf": DEFAULT_RF,
            "n_samples_per_point": args.n_samples,
            "n_warmup": N_WARMUP,
            "random_state": RANDOM_STATE,
            "note": "Single-flow calls, never batched, matching the live sniffer's one-flow-at-a-time "
                    "call pattern. tc/iptables enforcement latency is not re-measured here; it is "
                    "independent of n_packets (see Table 7 of the paper).",
        },
        "latency_by_n_packets": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[save] -> {args.out}")


if __name__ == "__main__":
    main()
