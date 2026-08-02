"""
Phase 2: real-time router AI sniffer + QoS enforcement.

Sniffs live traffic on --iface, tracks each flow's first N packets (N =
n_packets from the trained model bundle, 10 by default), and the moment the
N-th packet of a flow arrives, extracts SPLT features with the exact same
common.splt_features.extract_splt_features used in training, predicts the
QoS class, and installs a persistent tc/iptables rule (via QoSManager) that
routes the rest of that flow into the matching HTB class.

Requires root (raw-socket capture + tc/iptables) unless --dry-run is given.
Point --iface at a router's own interface (a Containernet/veth interface,
not a personal machine's primary NIC) -- see router/tc_manager.py.

Usage:
    sudo python sniffer.py --iface r-eth1
    sudo python sniffer.py --iface r-eth1 --dry-run     # log tc/iptables commands, don't execute
    sudo python sniffer.py --iface r-eth1 --no-enforce  # classify + log only, no tc/iptables at all
"""

import argparse
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.splt_features import extract_splt_features
from router.flow_tracker import FlowTracker
from router.tc_manager import QoSManager

PROTO_NAMES = {6: "tcp", 17: "udp"}


def load_model_bundle(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iface", required=True, help="interface to sniff and shape")
    parser.add_argument(
        "--model", type=Path, default=Path(__file__).resolve().parents[1] / "models" / "qos_classifier.pkl"
    )
    parser.add_argument("--total-rate-mbit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="log tc/iptables commands instead of executing them")
    parser.add_argument("--no-enforce", action="store_true", help="classify and log only, skip QoS setup entirely")
    parser.add_argument("--log-file", type=Path, default=None)
    args = parser.parse_args()

    from scapy.all import IP, TCP, UDP, sniff  # imported here so --help works without scapy installed

    bundle = load_model_bundle(args.model)
    model = bundle["model"]
    label_encoder = bundle["label_encoder"]
    n_packets = bundle["n_packets"]
    print(f"[sniffer] loaded {bundle['model_type']} model (n_packets={n_packets}, trained_at={bundle['trained_at']})")

    tracker = FlowTracker(n_packets=n_packets)
    qos = None
    if not args.no_enforce:
        qos = QoSManager(iface=args.iface, total_rate_mbit=args.total_rate_mbit, dry_run=args.dry_run)
        qos.setup()

    log_fh = open(args.log_file, "a") if args.log_file else None

    def handle_packet(pkt):
        if IP not in pkt:
            return
        ip_layer = pkt[IP]
        if TCP in pkt:
            proto, sport, dport = 6, int(pkt[TCP].sport), int(pkt[TCP].dport)
        elif UDP in pkt:
            proto, sport, dport = 17, int(pkt[UDP].sport), int(pkt[UDP].dport)
        else:
            return

        t_arrival = time.time()
        # Transport-layer bytes (header + payload, excludes the IP header) --
        # matches the NFStream accounting_mode=2 used to build the training data.
        size = len(ip_layer.payload)

        result = tracker.ingest(ip_layer.src, ip_layer.dst, sport, dport, proto, size, t_arrival)
        if result is None:
            return
        _key, flow, sizes, directions, piats = result

        features = extract_splt_features(sizes, directions, piats, n_packets=n_packets).reshape(1, -1)
        t_features = time.time()
        pred_idx = model.predict(features)[0]
        qos_class = label_encoder.inverse_transform([pred_idx])[0]
        t_predict = time.time()

        if qos is not None:
            qos.apply_qos_for_flow(
                flow["proto"], flow["orig_src"], flow["orig_dst"], flow["orig_sport"], flow["orig_dport"], qos_class
            )
        t_enforce = time.time()

        line = (
            f"{flow['orig_src']}:{flow['orig_sport']} -> {flow['orig_dst']}:{flow['orig_dport']} "
            f"proto={PROTO_NAMES.get(flow['proto'], flow['proto'])} class={qos_class} "
            f"feature_ms={1000 * (t_features - t_arrival):.3f} "
            f"predict_ms={1000 * (t_predict - t_features):.3f} "
            f"enforce_ms={1000 * (t_enforce - t_predict):.3f} "
            f"total_ms={1000 * (t_enforce - t_arrival):.3f}"
        )
        print(line)
        if log_fh:
            log_fh.write(line + "\n")
            log_fh.flush()

    bpf_filter = "tcp or udp"
    print(f"[sniffer] listening on {args.iface} (filter: '{bpf_filter}'); classifying at packet #{n_packets}")
    try:
        sniff(iface=args.iface, filter=bpf_filter, prn=handle_packet, store=False)
    finally:
        if qos is not None:
            print("[sniffer] tearing down QoS configuration...")
            qos.teardown()
        if log_fh:
            log_fh.close()


if __name__ == "__main__":
    main()
