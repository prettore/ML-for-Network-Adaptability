#!/usr/bin/env python3
"""
Phase 3 Containernet topology: 4 QoS traffic-generating clients + 1 router
(running the Phase 2 sniffer/tc enforcement) + 1 server.

    h_delay --\
    h_video ---\
    h_bulk  ---- s1 (switch) --- router --- server
    h_web   ---/

Client-to-switch and switch-to-router links: generous bandwidth
(--lan-mbit, default 1000), representing the LAN side.
Router-to-server link: constrained (--bottleneck-mbit, default 100) -- this
is the bottleneck where QoSManager's tc hierarchy is installed, i.e. the
`--iface` the Phase 2 sniffer points at ("router-wan" below).

NOTE: this requires the `containernet` fork of Mininet to be installed
(it replaces the `mininet` Python package with one that adds
`Containernet`/`addDocker`/`Docker`), root privileges (raw network
namespace/veth operations), and the two images built from
docker/router.Dockerfile and docker/traffic.Dockerfile. See the Phase 3
README section for build/install steps.

Run:
    sudo python3 topology.py                  # builds topology, then runs the full experiment
    sudo python3 topology.py --cli            # builds topology, drops into the Mininet CLI instead
"""

import argparse
import sys
from pathlib import Path

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Containernet
from mininet.node import Controller

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROUTER_IMAGE = "qos-testbed-router:latest"
TRAFFIC_IMAGE = "qos-testbed-traffic:latest"
CLIENT_NAMES = ["h_delay", "h_video", "h_bulk", "h_web"]
ROUTER_WAN_IFACE = "router-wan"


def build_and_start(bottleneck_mbit=100, lan_mbit=1000):
    net = Containernet(controller=Controller, link=TCLink)
    net.addController("c0")

    info("*** Adding docker hosts\n")
    router = net.addDocker(
        "router", ip="10.0.0.254/24", dimage=ROUTER_IMAGE, dcmd="sleep infinity", cap_add=["net_admin", "net_raw"]
    )
    server = net.addDocker("server", ip="10.0.1.1/24", dimage=TRAFFIC_IMAGE, dcmd="sleep infinity")
    clients = {
        name: net.addDocker(name, ip=f"10.0.0.{i + 1}/24", dimage=TRAFFIC_IMAGE, dcmd="sleep infinity")
        for i, name in enumerate(CLIENT_NAMES)
    }

    info("*** Adding switch and links\n")
    switch = net.addSwitch("s1")
    for host in clients.values():
        net.addLink(host, switch, cls=TCLink, bw=lan_mbit)
    net.addLink(switch, router, cls=TCLink, bw=lan_mbit, intfName2="router-lan")
    net.addLink(router, server, cls=TCLink, bw=bottleneck_mbit, intfName1=ROUTER_WAN_IFACE, intfName2="server-eth0")

    info("*** Starting network\n")
    net.start()

    info("*** Configuring routing\n")
    router.cmd("sysctl -w net.ipv4.ip_forward=1")
    router.cmd(f"ip addr add 10.0.1.254/24 dev {ROUTER_WAN_IFACE}")
    for host in clients.values():
        host.cmd("ip route add default via 10.0.0.254")
    server.cmd("ip route add default via 10.0.1.254")

    return net, clients, server, router


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bottleneck-mbit", type=int, default=100)
    parser.add_argument("--lan-mbit", type=int, default=1000)
    parser.add_argument("--duration-sec", type=int, default=15, help="D-ITG send duration per phase")
    parser.add_argument("--cli", action="store_true", help="drop into the Mininet CLI instead of running the experiment")
    args = parser.parse_args()

    setLogLevel("info")
    net, clients, server, router = build_and_start(args.bottleneck_mbit, args.lan_mbit)
    try:
        if args.cli:
            CLI(net)
        else:
            from run_experiment import run_experiment

            run_experiment(
                clients=clients,
                server=server,
                router=router,
                router_wan_iface=ROUTER_WAN_IFACE,
                bottleneck_mbit=args.bottleneck_mbit,
                duration_sec=args.duration_sec,
            )
    finally:
        net.stop()


if __name__ == "__main__":
    main()
