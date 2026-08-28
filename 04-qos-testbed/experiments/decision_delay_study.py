"""
How long does a router actually wait for n_packets to arrive, in real
wall-clock milliseconds, and how does that change with the feature-window
length?

ablation_study.py's n_packets sweep (Table 4 of the paper) answers "how much
accuracy and flow coverage do we gain or lose," and latency_study.py answers
"does the classifier's own compute cost change." Neither answers the
question a supervisor is most likely to actually ask: does waiting for
n_packets=8 instead of n_packets=10 meaningfully change how fast real
Delay-Sensitive traffic gets protected?

We cannot get this from the QoS pilot testbed's before/after delay numbers
(Table 9 in the paper): that experiment drives enforcement from the D-ITG
flows' ground-truth port, not from the live classifier's own n_packets-based
decision timing, specifically to isolate enforcement effectiveness from
classifier behavior (see Section 4.5 / sec:qos-pilot). D-ITG's synthetic
traffic also does not resemble real applications closely enough for its
timing to be representative (Section 4.6's domain-gap finding). So instead
of a synthetic pilot re-run, we compute this directly from the real dataset:
the exact same 429,597 real flows used throughout this project already
record each packet's real inter-arrival time (splt_piat_ms). Summing the
first n_packets-1 gaps gives the true wall-clock time from a flow's first
packet until its n_packets-th packet arrives -- the real time a router must
wait before it has enough information to classify that flow at all, before
even the ~12ms of model compute (latency_study.py) or the ~29ms full
sniffer pipeline (Table 7) on top.

Usage:
    python3 decision_delay_study.py [--data-path PATH] [--out results.json]
"""

import argparse
import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.qos_mapping import QOS_CLASSES, map_to_qos_class

MIN_APPLICATION_CONFIDENCE = 6
N_PACKETS_GRID = [5, 8, 10, 12, 15, 20]

# Measured elsewhere in this project, reused here rather than re-measured.
COMPUTE_LATENCY_MS = 12.6  # latency_study.py, mean total across the n_packets grid
FULL_PIPELINE_LATENCY_MS = 28.9  # Table 7, live sniffer incl. tc/iptables installation


def _parse_list(value):
    if isinstance(value, str):
        return ast.literal_eval(value)
    return list(value) if value is not None else []


def time_to_nth_packet_ms(piat_str, n_packets):
    """Wall-clock time from packet 1 to packet n_packets, i.e. the sum of
    the first (n_packets - 1) real inter-arrival gaps."""
    piat = _parse_list(piat_str)[:n_packets]
    valid = [p for p in piat[1:] if p is not None and p != -1]
    return float(np.sum(valid)) if valid else float("nan")


def load_cleaned(data_path):
    df = pd.read_parquet(data_path)
    df = df[df["application_is_guessed"] == 0]
    df = df[df["application_confidence"] == MIN_APPLICATION_CONFIDENCE]
    df = df[df["application_name"] != "Unknown"].copy()
    unmapped = set()
    df["qos_class"] = [
        map_to_qos_class(name, cat, unmapped)
        for name, cat in zip(df["application_name"], df["application_category_name"])
    ]
    print(f"[data] {len(df):,} DPI-confident flows (packet-count filter applied per n_packets below)")
    return df


def run(df):
    results = {}
    for n_packets in N_PACKETS_GRID:
        eligible = df[df["bidirectional_packets"] >= n_packets]
        wait_ms = eligible["splt_piat_ms"].apply(lambda s: time_to_nth_packet_ms(s, n_packets))
        eligible = eligible.assign(wait_ms=wait_ms)

        per_class = {}
        for cls in QOS_CLASSES:
            vals = eligible.loc[eligible["qos_class"] == cls, "wait_ms"].dropna()
            per_class[cls] = {
                "n_flows": int(len(vals)),
                "median_ms": float(vals.median()) if len(vals) else None,
                "mean_ms": float(vals.mean()) if len(vals) else None,
                "p90_ms": float(vals.quantile(0.90)) if len(vals) else None,
            }

        overall = eligible["wait_ms"].dropna()
        results[str(n_packets)] = {
            "overall": {
                "n_flows": int(len(overall)),
                "median_ms": float(overall.median()),
                "mean_ms": float(overall.mean()),
                "p90_ms": float(overall.quantile(0.90)),
            },
            "per_class": per_class,
        }
        print(
            f"  n_packets={n_packets:2d}  overall median wait={results[str(n_packets)]['overall']['median_ms']:7.2f}ms"
            f"  Delay-Sensitive median wait={per_class['Delay-Sensitive']['median_ms']:7.2f}ms"
            f"  (+{COMPUTE_LATENCY_MS}ms compute -> total {per_class['Delay-Sensitive']['median_ms'] + COMPUTE_LATENCY_MS:7.2f}ms to protection)"
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-path", type=Path,
        default=Path(__file__).resolve().parents[2] / "02-app-classification" / "data" / "data.parquet",
    )
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "decision_delay_results.json")
    args = parser.parse_args()

    df = load_cleaned(args.data_path)
    results = run(df)

    out = {
        "config": {
            "n_packets_grid": N_PACKETS_GRID,
            "compute_latency_ms": COMPUTE_LATENCY_MS,
            "full_pipeline_latency_ms": FULL_PIPELINE_LATENCY_MS,
            "note": "wait_ms is the sum of real measured inter-arrival gaps (splt_piat_ms) from packet 1 "
                    "to packet n_packets for each real flow, i.e. true wall-clock time before a router "
                    "could even attempt classification, not simulated or estimated from a fixed packet rate.",
        },
        "results_by_n_packets": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[save] -> {args.out}")


if __name__ == "__main__":
    main()
