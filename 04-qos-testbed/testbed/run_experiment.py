"""
Phase 3 experiment orchestration: run the 4 QoS-class D-ITG traffic
profiles concurrently in two phases against the same topology --

  - "baseline":    router's sniffer classifies each flow but does NOT
                   enforce QoS (--no-enforce). tc uses the interface's
                   default (pfifo_fast), so all 4 classes contend equally.
  - "qos_enabled": sniffer classifies AND enforces (tc HTB hierarchy +
                   iptables fwmark), so each class gets the QoS treatment
                   the model assigned it.

so the delta between the two phases isolates the effect of the QoS
mechanism itself. Called by topology.py after net.start(), while the
Containernet net (and its containers) are still alive. Collects all
container-side logs back to the host filesystem before returning, since
containers are torn down by topology.py's net.stop() afterward.
"""

import json
import time
from pathlib import Path

from ditg_scenarios import PROFILES, build_itgdec_cmd, build_itgsend_cmd

RECV_PORTS = {"Delay-Sensitive": 10001, "Video-Streaming": 10002, "Bulk-Download": 10003, "Web-Browsing": 10004}
CLIENT_TO_CLASS = {
    "h_delay": "Delay-Sensitive",
    "h_video": "Video-Streaming",
    "h_bulk": "Bulk-Download",
    "h_web": "Web-Browsing",
}
REMOTE_LOG_DIR = "/tmp/qos_testbed_logs"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _collect(node, remote_path, local_path):
    content = node.cmd(f"cat {remote_path} 2>/dev/null")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(content)


def _run_phase(clients, server, router, phase_name, duration_sec, enforce, router_wan_iface):
    print(f"[experiment] === phase: {phase_name} (enforce={enforce}) ===")
    for node in [server, router, *clients.values()]:
        node.cmd(f"mkdir -p {REMOTE_LOG_DIR}")

    sniffer_log = f"{REMOTE_LOG_DIR}/sniffer_{phase_name}.log"
    enforce_flag = "" if enforce else "--no-enforce"
    router.cmd(
        f"cd /app && python3 router/sniffer.py --iface {router_wan_iface} {enforce_flag} "
        f"--log-file {sniffer_log} > {REMOTE_LOG_DIR}/sniffer_{phase_name}.out 2>&1 &"
    )
    time.sleep(2)  # let tc/iptables setup (if enforcing) finish before traffic starts

    server.cmd(f"ITGRecv > {REMOTE_LOG_DIR}/itgrecv_{phase_name}.out 2>&1 &")
    time.sleep(1)

    server_ip = "10.0.1.1"
    remote_recv_logs = {}
    for name, host in clients.items():
        qos_class = CLIENT_TO_CLASS[name]
        profile = PROFILES[qos_class]
        remote_log = f"{REMOTE_LOG_DIR}/recv_{qos_class}_{phase_name}.log"
        remote_recv_logs[qos_class] = remote_log
        cmd = build_itgsend_cmd(profile, server_ip, RECV_PORTS[qos_class], duration_sec * 1000, remote_log)
        host.cmd(" ".join(cmd) + f" > {REMOTE_LOG_DIR}/send_{qos_class}_{phase_name}.out 2>&1 &")

    time.sleep(duration_sec + 3)

    router.cmd("pkill -f router/sniffer.py")
    time.sleep(1)

    local_dir = RESULTS_DIR / phase_name
    remote_summaries, remote_csvs = {}, {}
    for qos_class, remote_log in remote_recv_logs.items():
        remote_summary = f"{REMOTE_LOG_DIR}/dec_{qos_class}_{phase_name}.txt"
        remote_csv = f"{REMOTE_LOG_DIR}/dec_{qos_class}_{phase_name}.csv"
        server.cmd(" ".join(build_itgdec_cmd(remote_log)) + f" > {remote_summary}")
        server.cmd(" ".join(build_itgdec_cmd(remote_log, window_ms=1000, out_csv=remote_csv)))
        remote_summaries[qos_class] = remote_summary
        remote_csvs[qos_class] = remote_csv

    server.cmd("pkill ITGRecv")

    _collect(router, sniffer_log, local_dir / "sniffer.log")
    for qos_class in remote_summaries:
        _collect(server, remote_summaries[qos_class], local_dir / f"dec_{qos_class}.txt")
        _collect(server, remote_csvs[qos_class], local_dir / f"dec_{qos_class}.csv")

    return {
        "sniffer_log": str(local_dir / "sniffer.log"),
        "decoded_summaries": {c: str(local_dir / f"dec_{c}.txt") for c in remote_summaries},
        "decoded_csvs": {c: str(local_dir / f"dec_{c}.csv") for c in remote_csvs},
    }


def run_experiment(clients, server, router, router_wan_iface, bottleneck_mbit, duration_sec):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"bottleneck_mbit": bottleneck_mbit, "duration_sec": duration_sec, "phases": {}}

    manifest["phases"]["baseline"] = _run_phase(
        clients, server, router, "baseline", duration_sec, enforce=False, router_wan_iface=router_wan_iface
    )
    time.sleep(2)
    manifest["phases"]["qos_enabled"] = _run_phase(
        clients, server, router, "qos_enabled", duration_sec, enforce=True, router_wan_iface=router_wan_iface
    )

    manifest_path = RESULTS_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[experiment] done. manifest -> {manifest_path}")
    print("[experiment] run `python3 evaluate.py` to build the final Phase 3 report from it.")
    return manifest
