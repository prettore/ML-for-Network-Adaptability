"""
Builds and tears down a Linux HTB (Hierarchical Token Bucket) class
hierarchy on one egress interface, and dynamically routes individual flows
into the right class via iptables fwmark rules keyed on the flow's 5-tuple.

Design:
  - One root HTB qdisc with 4 leaf classes, one per QoS class, each with an
    SFQ leaf qdisc (so multiple concurrent flows within the same class are
    scheduled fairly rather than one flow starving the others).
  - Delay-Sensitive gets the highest priority (served first) so its queuing
    delay stays low; Video-Streaming gets the largest guaranteed rate;
    Bulk-Download gets the lowest priority/rate but can still burst up to
    the link ceiling when it's idle.
  - Classification happens once per flow (see FlowTracker); enforcement is
    "install a persistent iptables MARK rule for this 5-tuple", not
    per-packet, so steady-state overhead is a single netfilter table walk
    per packet rather than a per-packet ML inference.

This intentionally runs against a single interface you name explicitly
(--iface). Point it at a router's WAN-facing/bottleneck interface. It is
NOT meant to be pointed at a machine's primary desktop NIC -- `tc qdisc add
... root` replaces that interface's entire existing queueing discipline.
Use a dedicated router container/VM/veth (e.g. the Phase 3 Containernet
testbed) or --dry-run to inspect the commands without executing them.
"""

import ipaddress
import os
import shutil
import subprocess

QOS_CLASS_TO_TC = {
    # classid, mark, prio (0 = served first), guaranteed rate / ceil as a
    # fraction of total_rate_mbit (ceil_frac=None means "up to the full link
    # rate"). Fractions -- not absolute rates -- so this hierarchy scales
    # correctly regardless of the link's actual total_rate_mbit.
    "Delay-Sensitive": {"classid": "1:10", "mark": 10, "prio": 0, "rate_frac": 0.30, "ceil_frac": None},
    "Video-Streaming": {"classid": "1:20", "mark": 20, "prio": 1, "rate_frac": 0.40, "ceil_frac": None},
    "Web-Browsing": {"classid": "1:40", "mark": 40, "prio": 2, "rate_frac": 0.20, "ceil_frac": None},
    "Bulk-Download": {"classid": "1:30", "mark": 30, "prio": 3, "rate_frac": 0.10, "ceil_frac": 0.20},
}


def _validate_ip(value):
    ipaddress.ip_address(value)  # raises ValueError on malformed input
    return value


def _validate_port(value):
    port = int(value)
    if not 0 <= port <= 65535:
        raise ValueError(f"port out of range: {port}")
    return port


class QoSManager:
    def __init__(self, iface, total_rate_mbit=100, dry_run=False, chain_name="QOS_SNIFFER"):
        self.iface = iface
        self.total_rate_mbit = total_rate_mbit
        self.dry_run = dry_run
        self.chain_name = chain_name

        if not dry_run:
            if os.geteuid() != 0:
                raise PermissionError("tc/iptables enforcement requires root (or --dry-run to preview commands)")
            for binary in ("tc", "iptables"):
                if shutil.which(binary) is None:
                    raise RuntimeError(f"required binary '{binary}' not found on PATH")

    def _run(self, cmd, check=True):
        if self.dry_run:
            print("[dry-run]", " ".join(cmd))
            return None
        return subprocess.run(cmd, check=check, capture_output=True, text=True)

    def setup(self):
        # Clear any prior qdisc on this interface; errors here just mean there
        # was nothing to clear, which is fine.
        self._run(["tc", "qdisc", "del", "dev", self.iface, "root"], check=False)

        self._run(["tc", "qdisc", "add", "dev", self.iface, "root", "handle", "1:", "htb", "default", "40"])
        self._run(
            [
                "tc", "class", "add", "dev", self.iface, "parent", "1:", "classid", "1:1",
                "htb", "rate", f"{self.total_rate_mbit}mbit", "ceil", f"{self.total_rate_mbit}mbit",
            ]
        )

        for qos_class, cfg in QOS_CLASS_TO_TC.items():
            rate_mbit = max(1, round(self.total_rate_mbit * cfg["rate_frac"]))
            ceil_mbit = (
                max(rate_mbit, round(self.total_rate_mbit * cfg["ceil_frac"]))
                if cfg["ceil_frac"] is not None
                else self.total_rate_mbit
            )
            self._run(
                [
                    "tc", "class", "add", "dev", self.iface, "parent", "1:1", "classid", cfg["classid"],
                    "htb", "rate", f"{rate_mbit}mbit", "ceil", f"{ceil_mbit}mbit", "prio", str(cfg["prio"]),
                ]
            )
            handle = cfg["classid"].split(":")[1]
            self._run(
                ["tc", "qdisc", "add", "dev", self.iface, "parent", cfg["classid"], "handle", f"{handle}:", "sfq", "perturb", "10"]
            )
            self._run(
                [
                    "tc", "filter", "add", "dev", self.iface, "protocol", "ip", "parent", "1:0",
                    "prio", "1", "handle", str(cfg["mark"]), "fw", "flowid", cfg["classid"],
                ]
            )

        self._run(["iptables", "-t", "mangle", "-N", self.chain_name], check=False)
        self._run(["iptables", "-t", "mangle", "-F", self.chain_name])
        result = self._run(["iptables", "-t", "mangle", "-C", "FORWARD", "-j", self.chain_name], check=False)
        if self.dry_run or (result is not None and result.returncode != 0):
            self._run(["iptables", "-t", "mangle", "-A", "FORWARD", "-j", self.chain_name])

    def apply_qos_for_flow(self, proto, src_ip, dst_ip, sport, dport, qos_class):
        if qos_class not in QOS_CLASS_TO_TC:
            raise ValueError(f"unknown QoS class: {qos_class}")

        src_ip, dst_ip = _validate_ip(src_ip), _validate_ip(dst_ip)
        sport, dport = _validate_port(sport), _validate_port(dport)
        proto_name = {6: "tcp", 17: "udp"}.get(proto)
        if proto_name is None:
            raise ValueError(f"unsupported protocol number: {proto}")

        mark = str(QOS_CLASS_TO_TC[qos_class]["mark"])
        for s_ip, d_ip, s_port, d_port in ((src_ip, dst_ip, sport, dport), (dst_ip, src_ip, dport, sport)):
            self._run(
                [
                    "iptables", "-t", "mangle", "-A", self.chain_name,
                    "-p", proto_name, "-s", s_ip, "-d", d_ip,
                    "--sport", str(s_port), "--dport", str(d_port),
                    "-j", "MARK", "--set-mark", mark,
                ]
            )

    def teardown(self):
        self._run(["tc", "qdisc", "del", "dev", self.iface, "root"], check=False)
        self._run(["iptables", "-t", "mangle", "-D", "FORWARD", "-j", self.chain_name], check=False)
        self._run(["iptables", "-t", "mangle", "-F", self.chain_name], check=False)
        self._run(["iptables", "-t", "mangle", "-X", self.chain_name], check=False)
