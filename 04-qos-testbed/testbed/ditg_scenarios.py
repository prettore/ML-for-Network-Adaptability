"""
D-ITG traffic profiles for the 4 QoS classes, and ITGSend/ITGRecv/ITGDec
command builders. Runs inside the traffic-generator container (see
docker/traffic.Dockerfile); invoked remotely by run_experiment.py via
Containernet's host.cmd(), or directly for local testing.

Profile parameters are chosen to produce plausibly distinct traffic
patterns for each QoS class, and to create genuine contention for the
router's tc hierarchy to resolve:
  - Delay-Sensitive: small packets, high rate, low volume (VoIP-like) --
    latency-critical, not bandwidth-hungry.
  - Video-Streaming: large packets, sustained high rate -- needs
    consistent throughput.
  - Bulk-Download: max-size packets, greedy/maximal rate -- throughput-
    bound, delay-tolerant.
  - Web-Browsing: medium packets, bursty on/off pattern (short send burst,
    then idle) -- intermittent, low average rate. The on/off cycling is
    driven by the caller (run_experiment.py) issuing repeated short sends
    rather than by D-ITG itself.
"""

import argparse
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class TrafficProfile:
    qos_class: str
    protocol: str  # "UDP" or "TCP"
    packet_size: int  # bytes
    rate_pps: int  # packets per second
    burst: bool = False  # if True, caller alternates short send bursts with idle gaps


PROFILES = {
    "Delay-Sensitive": TrafficProfile("Delay-Sensitive", "UDP", 160, 50),
    "Video-Streaming": TrafficProfile("Video-Streaming", "UDP", 1400, 400),
    "Bulk-Download": TrafficProfile("Bulk-Download", "TCP", 1400, 900),
    "Web-Browsing": TrafficProfile("Web-Browsing", "TCP", 800, 60, burst=True),
}


def build_itgrecv_cmd(log_file):
    return ["ITGRecv", "-l", log_file]


def build_itgsend_cmd(profile, dst_ip, recv_port, duration_ms, receiver_log):
    return [
        "ITGSend",
        "-a", dst_ip,
        "-rp", str(recv_port),
        "-T", profile.protocol,
        "-c", str(profile.packet_size),
        "-C", str(profile.rate_pps),
        "-t", str(duration_ms),
        "-x", receiver_log,
    ]


def build_itgdec_cmd(log_file, window_ms=None, out_csv=None):
    cmd = ["ITGDec", log_file]
    if window_ms is not None and out_csv is not None:
        cmd += ["-c", str(window_ms), out_csv]
    return cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    recv = sub.add_parser("recv", help="start an ITGRecv listener")
    recv.add_argument("--log-file", required=True)

    send = sub.add_parser("send", help="run one ITGSend burst for a QoS class profile")
    send.add_argument("--qos-class", required=True, choices=list(PROFILES))
    send.add_argument("--dst", required=True)
    send.add_argument("--recv-port", type=int, default=9999)
    send.add_argument("--duration-ms", type=int, default=10000)
    send.add_argument("--receiver-log", required=True)

    dec = sub.add_parser("dec", help="decode an ITG log into human-readable / CSV stats")
    dec.add_argument("--log-file", required=True)
    dec.add_argument("--window-ms", type=int, default=None)
    dec.add_argument("--out-csv", default=None)

    args = parser.parse_args()
    if args.mode == "recv":
        cmd = build_itgrecv_cmd(args.log_file)
    elif args.mode == "send":
        cmd = build_itgsend_cmd(PROFILES[args.qos_class], args.dst, args.recv_port, args.duration_ms, args.receiver_log)
    else:
        cmd = build_itgdec_cmd(args.log_file, args.window_ms, args.out_csv)

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
