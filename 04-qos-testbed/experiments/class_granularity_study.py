"""
Class-granularity ablation: is 4 QoS classes a reasonable choice, or would
a coarser or finer taxonomy classify better? We define four taxonomies at
different granularities from the SAME underlying nDPI
application_category_name signal (and the same 6 service-name overrides,
regrouped to match each taxonomy), train an identical Random Forest
(the deployed hyperparameters, n_packets=10) on each, and compare macro F1
-- holding features, model, and train/test split methodology fixed so
only class granularity varies.

Taxonomies (coarsest to finest):
  2-class: Latency-Critical (current Delay-Sensitive + Video-Streaming)
           vs Best-Effort (current Bulk-Download + Web-Browsing)
  3-class: Delay-Sensitive, Video-Streaming, Best-Effort
           (current Bulk-Download + Web-Browsing merged -- the classic
           voice/video/data three-tier QoS model)
  4-class: the deployed taxonomy (common/qos_mapping.py), included here
           unchanged as the center point of the comparison
  6-class: Delay-Sensitive split into three: Real-Time-Communication
           (VoIP/Chat/Collaborative), Network-Control (RemoteAccess/
           Network/ConnCheck/Database/VirtAssistant/RPC), and
           Interactive-Gaming (Game) -- testing whether the traffic this
           project currently lumps into one "interactive" bucket is
           actually distinguishable at the SPLT level, and whether
           separating it costs or gains accuracy.

Usage:
    python3 class_granularity_study.py [--data-path PATH] [--out results.json]
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

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.splt_features import build_feature_matrix

MIN_APPLICATION_CONFIDENCE = 6
RANDOM_STATE = 42
CV_SPLITS = 5
N_PACKETS = 10
DEPLOYED_RF = {"n_estimators": 100, "max_depth": 22, "min_samples_leaf": 3}

# -- Taxonomy definitions -----------------------------------------------
# Each is (service_overrides, category_map, default_class), mirroring
# common/qos_mapping.py's structure exactly but regrouped per taxonomy.

TAXONOMY_2 = (
    {"steam": "Best-Effort", "epicgames": "Best-Effort", "blizzard": "Best-Effort",
     "electronicarts": "Best-Effort", "tiktok": "Latency-Critical", "fbookreelstory": "Latency-Critical"},
    {c: "Latency-Critical" for c in [
        "VoIP", "Chat", "Collaborative", "RemoteAccess", "Network", "ConnCheck", "Game",
        "Database", "VirtAssistant", "RPC", "Media", "Video", "Streaming", "Music",
    ]},
    "Best-Effort",
)

TAXONOMY_3 = (
    {"steam": "Best-Effort", "epicgames": "Best-Effort", "blizzard": "Best-Effort",
     "electronicarts": "Best-Effort", "tiktok": "Video-Streaming", "fbookreelstory": "Video-Streaming"},
    {
        **{c: "Delay-Sensitive" for c in ["VoIP", "Chat", "Collaborative", "RemoteAccess", "Network",
                                           "ConnCheck", "Game", "Database", "VirtAssistant", "RPC"]},
        **{c: "Video-Streaming" for c in ["Media", "Video", "Streaming", "Music"]},
    },
    "Best-Effort",  # SoftwareUpdate/Download/Cloud fall here too, same as the 4-class Web-Browsing default
)

# 4-class: imported directly from production code below, not redefined here.

TAXONOMY_6 = (
    {"steam": "Bulk-Download", "epicgames": "Bulk-Download", "blizzard": "Bulk-Download",
     "electronicarts": "Bulk-Download", "tiktok": "Video-Streaming", "fbookreelstory": "Video-Streaming"},
    {
        "VoIP": "Real-Time-Communication", "Chat": "Real-Time-Communication", "Collaborative": "Real-Time-Communication",
        "RemoteAccess": "Network-Control", "Network": "Network-Control", "ConnCheck": "Network-Control",
        "Database": "Network-Control", "VirtAssistant": "Network-Control", "RPC": "Network-Control",
        "Game": "Interactive-Gaming",
        "Media": "Video-Streaming", "Video": "Video-Streaming", "Streaming": "Video-Streaming", "Music": "Video-Streaming",
        "SoftwareUpdate": "Bulk-Download", "Download": "Bulk-Download", "Cloud": "Bulk-Download",
    },
    "Web-Browsing",
)


def map_class(application_name, application_category_name, service_overrides, category_map, default_class):
    service = str(application_name).split(".")[-1].strip().lower() if application_name else ""
    if service in service_overrides:
        return service_overrides[service]
    category = str(application_category_name).strip() if application_category_name else ""
    return category_map.get(category, default_class)


def load_base_cleaned(data_path):
    df = pd.read_parquet(data_path)
    df = df[df["application_is_guessed"] == 0]
    df = df[df["application_confidence"] == MIN_APPLICATION_CONFIDENCE]
    df = df[df["application_name"] != "Unknown"]
    df = df[df["bidirectional_packets"] >= N_PACKETS].copy()
    print(f"[data] {len(df):,} flows after standard cleaning + >= {N_PACKETS}-packet filter (shared across all taxonomies)")
    return df


def pickle_size_mb(model):
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        path = tf.name
    try:
        with open(path, "wb") as f:
            pickle.dump(model, f)
        return os.path.getsize(path) / 1e6
    finally:
        os.remove(path)


def evaluate_taxonomy(df, name, service_overrides, category_map, default_class):
    print(f"\n[taxonomy] {name}")
    labels = [
        map_class(n, c, service_overrides, category_map, default_class)
        for n, c in zip(df["application_name"], df["application_category_name"])
    ]
    classes = sorted(set(labels))
    print(f"  classes ({len(classes)}): {classes}")

    counts = pd.Series(labels).value_counts()
    for cls, n in counts.items():
        print(f"    {cls:<24} {n:>8,}  ({100 * n / len(df):5.1f}%)")

    X = build_feature_matrix(df, n_packets=N_PACKETS)
    label_encoder = LabelEncoder().fit(classes)
    y = label_encoder.transform(labels)
    groups = df["src_ip"].to_numpy()

    splitter = StratifiedGroupKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_train, X_test, y_train, y_test = X[train_idx], X[test_idx], y[train_idx], y[test_idx]

    model = RandomForestClassifier(class_weight="balanced", random_state=RANDOM_STATE, n_jobs=2, **DEPLOYED_RF)
    t0 = time.time()
    model.fit(X_train, y_train)
    train_seconds = time.time() - t0
    y_pred = model.predict(X_test)
    macro_f1 = f1_score(y_test, y_pred, average="macro")
    report = classification_report(y_test, y_pred, target_names=label_encoder.classes_, output_dict=True, zero_division=0)
    pickle_mb = pickle_size_mb(model)

    print(f"    -> macro_f1={macro_f1:.4f} accuracy={report['accuracy']:.4f} size={pickle_mb:.1f}MB train_time={train_seconds:.1f}s")
    for cls in label_encoder.classes_:
        print(f"       {cls:<24} F1={report[cls]['f1-score']:.4f}")

    result = {
        "n_classes": len(classes),
        "classes": classes,
        "class_distribution": counts.to_dict(),
        "macro_f1": macro_f1,
        "accuracy": report["accuracy"],
        "per_class_f1": {cls: report[cls]["f1-score"] for cls in label_encoder.classes_},
        "pickle_mb": pickle_mb,
        "train_seconds": train_seconds,
    }
    del model, y_pred, X
    gc.collect()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-path", type=Path,
        default=Path(__file__).resolve().parents[2] / "02-app-classification" / "data" / "data.parquet",
    )
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "class_granularity_results.json")
    args = parser.parse_args()

    df = load_base_cleaned(args.data_path)

    results = {}
    results["2"] = evaluate_taxonomy(df, "2-class (Latency-Critical / Best-Effort)", *TAXONOMY_2)
    results["3"] = evaluate_taxonomy(df, "3-class (Delay-Sensitive / Video-Streaming / Best-Effort)", *TAXONOMY_3)

    # 4-class: use the actual production mapping for full fidelity with the deployed system.
    from common.qos_mapping import SERVICE_OVERRIDES, CATEGORY_MAP, DEFAULT_CLASS
    results["4"] = evaluate_taxonomy(df, "4-class (deployed taxonomy)", SERVICE_OVERRIDES, CATEGORY_MAP, DEFAULT_CLASS)

    results["6"] = evaluate_taxonomy(df, "6-class (Delay-Sensitive split 3 ways)", *TAXONOMY_6)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[save] -> {args.out}")


if __name__ == "__main__":
    main()
