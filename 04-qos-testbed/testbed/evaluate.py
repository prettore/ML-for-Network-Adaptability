"""
Phase 3 evaluation harness: combines the 3 metrics the master plan calls
for into one report, reading from artifacts the earlier phases/scripts
already produce:

  1. ML accuracy/F1        -- 04-qos-testbed/models/phase1_metrics.json (Phase 1)
  2. Router processing latency -- results/<phase>/sniffer.log (Phase 2's
     per-flow feature/predict/enforce/total timing, written by
     router/sniffer.py --log-file)
  3. QoS improvement (delay/throughput before vs after enforcement) --
     results/<phase>/dec_<class>.txt (D-ITG's ITGDec summary output),
     compared between the "baseline" (--no-enforce) and "qos_enabled"
     phases run_experiment.py produces.

Usage:
    python3 evaluate.py [--results-dir results] [--phase1-metrics ../models/phase1_metrics.json]
                        [--out report.json]
"""

import argparse
import json
import re
import statistics
from pathlib import Path

SNIFFER_LINE_RE = re.compile(
    r"class=(?P<cls>\S+)\s+feature_ms=(?P<feature>[\d.]+)\s+predict_ms=(?P<predict>[\d.]+)\s+"
    r"enforce_ms=(?P<enforce>[\d.]+)\s+total_ms=(?P<total>[\d.]+)"
)

ITGDEC_PATTERNS = {
    "avg_delay_s": re.compile(r"Average delay\s*=\s*([\d.]+) s"),
    "avg_jitter_s": re.compile(r"Average jitter\s*=\s*([\d.]+) s"),
    "avg_bitrate_kbps": re.compile(r"Average bitrate\s*=\s*([\d.]+) Kbit/s"),
    "total_packets": re.compile(r"Total packets\s*=\s*(\d+)"),
    "packets_dropped": re.compile(r"Packets dropped\s*=\s*(\d+) \(([\d.]+) %\)"),
}


def _percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, int(round(pct / 100.0 * (len(values) - 1))))
    return values[idx]


def load_ml_metrics(phase1_metrics_path):
    with open(phase1_metrics_path) as f:
        metrics = json.load(f)
    selected = metrics["selected_model"]
    report = metrics["models"][selected]["classification_report"]
    return {
        "selected_model": selected,
        "macro_f1": metrics["models"][selected]["macro_f1"],
        "accuracy": report["accuracy"],
        "per_class_f1": {
            cls: report[str(idx)]["f1-score"]
            for idx, cls in enumerate(sorted(metrics["qos_class_distribution"]))
            if str(idx) in report
        },
        "n_flows_total": metrics["n_flows_total"],
    }


def parse_sniffer_log(log_path):
    totals, by_class = [], {}
    text = Path(log_path).read_text()
    for m in SNIFFER_LINE_RE.finditer(text):
        cls = m.group("cls")
        row = {k: float(m.group(k)) for k in ("feature", "predict", "enforce", "total")}
        totals.append(row["total"])
        by_class.setdefault(cls, []).append(row)

    def _stats(values):
        if not values:
            return None
        return {
            "n": len(values),
            "mean_ms": statistics.mean(values),
            "p50_ms": _percentile(values, 50),
            "p95_ms": _percentile(values, 95),
            "p99_ms": _percentile(values, 99),
            "max_ms": max(values),
        }

    return {
        "n_flows_classified": len(totals),
        "total_latency": _stats(totals),
        "per_class_count": {cls: len(rows) for cls, rows in by_class.items()},
    }


def parse_itgdec_summary(text):
    # Prefer the aggregate "TOTAL RESULTS" section if present (robust to
    # multiple flow IDs appearing in one log); fall back to the whole text.
    marker = "TOTAL RESULTS"
    section = text[text.index(marker):] if marker in text else text

    result = {}
    for key, pattern in ITGDEC_PATTERNS.items():
        match = pattern.search(section)
        if not match:
            result[key] = None
        elif key == "packets_dropped":
            result[key] = int(match.group(1))
            result["loss_pct"] = float(match.group(2))
        else:
            result[key] = float(match.group(1))
    return result


def build_qos_comparison(results_dir):
    comparison = {}
    baseline_dir = results_dir / "baseline"
    qos_dir = results_dir / "qos_enabled"
    if not baseline_dir.exists() or not qos_dir.exists():
        return comparison

    classes = sorted({p.stem.removeprefix("dec_") for p in baseline_dir.glob("dec_*.txt")})
    for cls in classes:
        baseline_file = baseline_dir / f"dec_{cls}.txt"
        qos_file = qos_dir / f"dec_{cls}.txt"
        if not baseline_file.exists() or not qos_file.exists():
            continue
        before = parse_itgdec_summary(baseline_file.read_text())
        after = parse_itgdec_summary(qos_file.read_text())
        delta = {}
        for key in ("avg_delay_s", "avg_jitter_s", "avg_bitrate_kbps", "loss_pct"):
            if before.get(key) is not None and after.get(key) is not None:
                delta[key] = after[key] - before[key]
        comparison[cls] = {"before": before, "after": after, "delta": delta}
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).resolve().parent / "results")
    parser.add_argument(
        "--phase1-metrics", type=Path, default=Path(__file__).resolve().parents[1] / "models" / "phase1_metrics.json"
    )
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results" / "phase3_report.json")
    args = parser.parse_args()

    report = {}
    if args.phase1_metrics.exists():
        report["ml_classification"] = load_ml_metrics(args.phase1_metrics)
    else:
        print(f"[evaluate] WARNING: {args.phase1_metrics} not found, skipping ML metrics section")

    for phase in ("baseline", "qos_enabled"):
        sniffer_log = args.results_dir / phase / "sniffer.log"
        if sniffer_log.exists():
            report.setdefault("router_latency", {})[phase] = parse_sniffer_log(sniffer_log)
        else:
            print(f"[evaluate] WARNING: {sniffer_log} not found, skipping")

    report["qos_before_after"] = build_qos_comparison(args.results_dir)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[evaluate] report written -> {args.out}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
