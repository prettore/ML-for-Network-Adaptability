"""
Compares three synthetic traffic generators, D-ITG, MGEN, and iperf3,
against real traffic on the one property that matters for an SPLT-based
early classifier: the shape of a flow's first 10 packets.

For each tool we captured a short loopback flow with the tool's own
default or documented profile (D-ITG: 50 pkt/s, 160 B UDP, matching the
Delay-Sensitive profile used elsewhere in this project; MGEN: an
equivalent PERIODIC [50 160] UDP event, chosen so the comparison holds
the target rate/size constant and isolates what differs structurally
between the tools rather than between arbitrary configurations; iperf3:
its own default TCP throughput test, since iperf3 has no notion of an
"early handshake" pattern to configure) and parsed the resulting pcap
with scapy to extract the same signed-size / inter-arrival-time signature
common/splt_features.py builds from real flows.

The comparison metric is the coefficient of variation (CV = std / mean)
of packet size across the first 10 packets of a flow. Real encrypted
application flows begin with a TLS or QUIC handshake, a sequence of
different-sized messages (ClientHello, ServerHello, certificate, Finished)
before settling into steady-state payload, so real flows show substantial
early-packet size variability. A synthetic generator that emits
fixed-size packets at a fixed or randomized rate, which is what all three
tools do by design, produces a first-10-packet CV near zero regardless of
how closely its aggregate rate and packet size are tuned to resemble a
target application, because none of the three implements anything
resembling a TLS handshake.

Capture (produces the three pcaps this script reads from --pcap-dir):
    on a host or container with d-itg, mgen, iperf3, and tcpdump installed,
    with segmentation offload disabled and MTU fixed to 1500 on the
    capture interface (loopback bypasses normal packetization otherwise):
        ip link set lo mtu 1500 && ethtool -K lo tso off gso off gro off
        tcpdump -i lo -w ditg.pcap -U 'udp port 8999' &
        ITGRecv &
        ITGSend -a 127.0.0.1 -T UDP -C 50 -c 160 -t 5000
        tcpdump -i lo -w mgen.pcap -U 'udp port 5000' &
        mgen port 5000 &
        mgen event 'ON 1 UDP DST 127.0.0.1/5000 PERIODIC [50 160]'
        tcpdump -i lo -w iperf3.pcap -c 60 -U 'tcp port 5201' &
        iperf3 -s -1 -p 5201 &
        iperf3 -c 127.0.0.1 -p 5201 -t 2
    Requires: pip install scapy

Usage:
    python3 synthetic_generator_comparison.py --pcap-dir DIR [--out results.json]
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scapy.all import IP, TCP, UDP, rdpcap

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

N_PACKETS = 10
DEFAULT_PCAP_DIR = Path(__file__).resolve().parent.parent.parent / "scratch_pcaps"

TOOLS = {
    "D-ITG": "ditg_fresh.pcap",
    "MGEN": "mgen.pcap",
    "iperf3": "iperf3.pcap",
}


def extract_flows(pcap_path):
    """Group packets into 5-tuple flows, first-seen source as forward direction."""
    packets = rdpcap(str(pcap_path))
    flows = defaultdict(list)
    flow_first_src = {}
    for pkt in packets:
        if IP not in pkt:
            continue
        proto = "TCP" if TCP in pkt else ("UDP" if UDP in pkt else None)
        if proto is None:
            continue
        l4 = pkt[TCP] if proto == "TCP" else pkt[UDP]
        a, b = (pkt[IP].src, l4.sport), (pkt[IP].dst, l4.dport)
        key = tuple(sorted([a, b])) + (proto,)
        if key not in flow_first_src:
            flow_first_src[key] = pkt[IP].src
        direction = 1 if pkt[IP].src == flow_first_src[key] else -1
        flows[key].append((float(pkt.time), direction, len(pkt)))
    return flows


def first_n_signature(flow_packets, n=N_PACKETS):
    flow_packets = sorted(flow_packets, key=lambda p: p[0])[:n]
    if len(flow_packets) < n:
        return None
    t0 = flow_packets[0][0]
    iat = [0.0] + [(flow_packets[i][0] - flow_packets[i - 1][0]) * 1000 for i in range(1, n)]
    signed_size = [p[2] * p[1] for p in flow_packets]
    return signed_size, iat


def analyze_tool(pcap_path, n=N_PACKETS):
    flows = extract_flows(pcap_path)
    if not flows:
        return None
    largest_flow_key = max(flows, key=lambda k: len(flows[k]))
    sig = first_n_signature(flows[largest_flow_key], n)
    if sig is None:
        return None
    signed_size, iat = sig
    abs_size = np.abs(signed_size)
    cv = float(np.std(abs_size) / np.mean(abs_size)) if np.mean(abs_size) > 0 else float("nan")
    return {
        "n_flows_in_capture": len(flows),
        "packets_in_largest_flow": len(flows[largest_flow_key]),
        "first_n_signed_size": [float(s) for s in signed_size],
        "first_n_iat_ms": [float(i) for i in iat],
        "size_coefficient_of_variation": cv,
        "size_mean": float(np.mean(abs_size)),
        "size_std": float(np.std(abs_size)),
    }


def real_data_reference_cv(data_path, n=N_PACKETS, n_flows_sample=5000, seed=42):
    """Same CV metric computed on a sample of real flows, for comparison."""
    import ast

    import pandas as pd

    df = pd.read_parquet(data_path)
    df = df[df["application_is_guessed"] == 0]
    df = df[df["application_confidence"] == 6]
    df = df[df["application_name"] != "Unknown"]
    df = df[df["bidirectional_packets"] >= n]
    df = df.sample(min(n_flows_sample, len(df)), random_state=seed)

    cvs = []
    for ps_str in df["splt_ps"]:
        ps = ast.literal_eval(ps_str)[:n] if isinstance(ps_str, str) else list(ps_str)[:n]
        ps = np.abs(np.array([p for p in ps if p != -1], dtype=float))
        if len(ps) == n and ps.mean() > 0:
            cvs.append(ps.std() / ps.mean())
    return {
        "n_flows_sampled": len(cvs),
        "median_cv": float(np.median(cvs)),
        "mean_cv": float(np.mean(cvs)),
        "p25_cv": float(np.percentile(cvs, 25)),
        "p75_cv": float(np.percentile(cvs, 75)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pcap-dir", type=Path, default=DEFAULT_PCAP_DIR)
    parser.add_argument(
        "--real-data-path", type=Path,
        default=Path(__file__).resolve().parents[2] / "02-app-classification" / "data" / "data.parquet",
    )
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "synthetic_generator_comparison_results.json")
    parser.add_argument(
        "--model-path", type=Path,
        default=Path(__file__).resolve().parents[1] / "models" / "qos_classifier.pkl",
    )
    args = parser.parse_args()

    import pickle
    with open(args.model_path, "rb") as f:
        bundle = pickle.load(f)
    model, label_encoder = bundle["model"], bundle["label_encoder"]

    results = {}
    for tool_name, pcap_file in TOOLS.items():
        pcap_path = args.pcap_dir / pcap_file
        print(f"[{tool_name}] analyzing {pcap_path}")
        res = analyze_tool(pcap_path)
        if res is None:
            print(f"  skipped: could not extract a {N_PACKETS}-packet flow")
            continue
        X = np.array([res["first_n_signed_size"] + res["first_n_iat_ms"]], dtype=np.float32)
        res["predicted_class"] = label_encoder.inverse_transform(model.predict(X))[0]
        results[tool_name] = res
        print(
            f"  CV(size) = {res['size_coefficient_of_variation']:.4f}  "
            f"predicted class = {res['predicted_class']}  first sizes: {res['first_n_signed_size']}"
        )

    print("\n[real data reference]")
    real_ref = real_data_reference_cv(args.real_data_path)
    print(f"  median CV(size) across {real_ref['n_flows_sampled']:,} real flows: {real_ref['median_cv']:.4f}")

    out = {"synthetic_tools": results, "real_data_reference": real_ref}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[save] -> {args.out}")


if __name__ == "__main__":
    main()
