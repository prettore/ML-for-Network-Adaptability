"""
External-dataset evaluation: does the deployed classifier, trained and
tuned entirely on our own university-network capture, generalize to a
real dataset it has never seen, collected by someone else, on a different
network, at a different time?

We use CESNET-TLS22 (Luxemburk & Cejka, 2023), a public dataset of
141.7M real TLS flows from the CESNET2 backbone, released via the
cesnet-datazoo package. Its per-flow PPI field records exactly what our
own SPLT feature does: [[inter-packet times], [packet directions],
[packet sizes]] for up to 30 packets, with direction encoded as +1/-1
(matching our own convention that the flow-initiating direction is
positive) and unused trailing positions zero-padded rather than our
NFStream pipeline's -1 sentinel. This structural similarity is what
makes a like-for-like evaluation possible without retraining: we map
CESNET's PPI directly onto our existing 20-dimensional feature vector
(common/splt_features.py's layout) and run our already-trained,
already-deployed Random Forest unchanged.

Label mapping: CESNET provides a 21-category taxonomy (Videoconferencing,
Streaming media, Software updates, ...), coarser and differently drawn
than nDPI's, so we map its CATEGORY field to our 4 QoS classes with the
same reasoning we used for our own taxonomy (common/qos_mapping.py),
plus two of the same principled service-level overrides: game-client
services (Steam, Xbox Live, EA, Riot, King, Unity) default to a "Games"
category but are dominated by client/patch downloads, so they are
reassigned to Bulk-Download; TikTok defaults to "Social" but carries
continuous short-form video, so it is reassigned to Video-Streaming.

We sample a subset of days from the CESNET-TLS22-XS split (not the full
141.7M-flow dataset) for tractable runtime; this is disclosed as a
limitation, not presented as exhaustive.

Setup (downloads the XS split, about 1.2\,GB, to --data-dir once):
    pip install cesnet-datazoo tables
    python3 -c "from cesnet_datazoo.datasets import CESNET_TLS22; \
        CESNET_TLS22('DIR', size='XS')"

Usage:
    python3 cesnet_external_eval.py --data-dir DIR [--days N] [--out results.json]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tables
from sklearn.metrics import classification_report, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.qos_mapping import QOS_CLASSES

N_PACKETS = 10
MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "qos_classifier.pkl"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "cesnet_data"

# CESNET-TLS22's own 21-category taxonomy -> our 4 QoS classes, using the
# same reasoning as common/qos_mapping.py's CATEGORY_MAP.
CESNET_CATEGORY_MAP = {
    "Videoconferencing": "Delay-Sensitive",
    "Instant messaging": "Delay-Sensitive",
    "Remote Desktop": "Delay-Sensitive",
    "Virtual assistant": "Delay-Sensitive",
    "Streaming media": "Video-Streaming",
    "Music": "Video-Streaming",
    "Software updates": "Bulk-Download",
    "File sharing": "Bulk-Download",
    # Everything else (Antivirus, Notification services, Authentication
    # services, Analytics & Telemetry, Search, Advertising, Other services
    # and APIs, Mail, Social, Games, Information Systems, Internet Banking,
    # Weather services, default) falls through to Web-Browsing below,
    # mirroring our own taxonomy's default-class design.
}
DEFAULT_CLASS = "Web-Browsing"

# Service-level overrides, same principled exceptions as our own taxonomy.
CESNET_APP_OVERRIDES = {
    "steam": "Bulk-Download", "xbox-live": "Bulk-Download", "ea-games": "Bulk-Download",
    "riot-games": "Bulk-Download", "king-games": "Bulk-Download", "unity-games": "Bulk-Download",
    "tiktok": "Video-Streaming",
}


def map_cesnet_class(app, category):
    if app in CESNET_APP_OVERRIDES:
        return CESNET_APP_OVERRIDES[app]
    return CESNET_CATEGORY_MAP.get(category, DEFAULT_CLASS)


def load_cesnet_days(data_dir, n_days):
    h5_path = data_dir / "XS" / "CESNET-TLS22-XS.h5"
    f = tables.open_file(str(h5_path), "r")
    day_nodes = sorted(n._v_name for n in f.list_nodes("/flows") if not n._v_name.startswith("_i_"))
    day_nodes = day_nodes[:n_days]
    print(f"[data] reading {n_days} day(s): {day_nodes}")

    app_enum = f.get_node(f"/flows/{day_nodes[0]}").get_enum("APP")
    category_enum = f.get_node(f"/flows/{day_nodes[0]}").get_enum("CATEGORY")
    app_lookup = {code: name for name, code in app_enum._names.items()}
    category_lookup = {code: name for name, code in category_enum._names.items()}

    chunks = []
    for day in day_nodes:
        t = f.get_node(f"/flows/{day}")
        data = t.read()
        data = data[data["PPI_LEN"] >= N_PACKETS]
        chunks.append(data)
        print(f"  {day}: {len(data):,} flows with >= {N_PACKETS} packets")
    f.close()

    all_data = np.concatenate(chunks)
    apps = np.array([app_lookup[c] for c in all_data["APP"]])
    categories = np.array([category_lookup[c] for c in all_data["CATEGORY"]])
    print(f"[data] {len(all_data):,} flows total with >= {N_PACKETS} packets")
    return all_data, apps, categories


def build_features_and_labels(data, apps, categories):
    ppi = data["PPI"][:, :, :N_PACKETS]  # (n, 3, N_PACKETS): iat, direction, size
    iat = ppi[:, 0, :]
    direction = ppi[:, 1, :]
    size = ppi[:, 2, :]
    signed_size = np.where(direction == 1, size, -size)
    X = np.concatenate([signed_size, iat], axis=1).astype(np.float32)
    labels = [map_cesnet_class(a, c) for a, c in zip(apps, categories)]
    return X, labels


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--days", type=int, default=3, help="number of CESNET-TLS22-XS days to sample")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "cesnet_eval_results.json")
    args = parser.parse_args()

    data, apps, categories = load_cesnet_days(args.data_dir, args.days)
    X, labels = build_features_and_labels(data, apps, categories)

    label_counts = pd.Series(labels).value_counts()
    print("[labels]")
    for cls, n in label_counts.items():
        print(f"  {cls:<18} {n:>8,}  ({100 * n / len(labels):5.1f}%)")

    print(f"\n[model] loading {MODEL_PATH}")
    import pickle
    with open(MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    label_encoder = bundle["label_encoder"]
    class_names = list(label_encoder.classes_)

    y_true = label_encoder.transform(labels)
    y_pred = model.predict(X)
    macro_f1 = f1_score(y_true, y_pred, average="macro")
    report = classification_report(y_true, y_pred, target_names=class_names, output_dict=True, zero_division=0)

    print(f"\n[result] macro_f1={macro_f1:.4f} accuracy={report['accuracy']:.4f} n={len(labels):,}")
    for cls in class_names:
        print(f"  {cls:<18} F1={report[cls]['f1-score']:.4f} support={int(report[cls]['support'])}")

    confusion = pd.crosstab(
        pd.Series([class_names[i] for i in y_true], name="true"),
        pd.Series([class_names[i] for i in y_pred], name="pred"),
    ).reindex(index=class_names, columns=class_names, fill_value=0)

    out = {
        "n_days_sampled": args.days,
        "n_flows": len(labels),
        "class_distribution": label_counts.to_dict(),
        "macro_f1": macro_f1,
        "accuracy": report["accuracy"],
        "per_class_f1": {cls: report[cls]["f1-score"] for cls in class_names},
        "per_class_precision": {cls: report[cls]["precision"] for cls in class_names},
        "per_class_recall": {cls: report[cls]["recall"] for cls in class_names},
        "confusion_matrix": confusion.to_dict(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n[save] -> {args.out}")


if __name__ == "__main__":
    main()
