"""
Tracks in-progress flows and accumulates their first N packets so a caller
can run early classification the moment enough packets have been seen.

A flow is keyed direction-agnostically (the same key is produced regardless
of which endpoint sent a given packet), but the *first* packet observed for
a key fixes the "original" src/dst -- matching NFStream's convention, where
splt_direction is 0 for packets flowing in the direction of that first
packet and 1 for the reverse.
"""

import time


class FlowTracker:
    def __init__(self, n_packets=10, flow_timeout=120.0):
        self.n_packets = n_packets
        self.flow_timeout = flow_timeout
        self.flows = {}
        self._packets_seen = 0

    @staticmethod
    def flow_key(src_ip, dst_ip, sport, dport, proto):
        if (src_ip, sport) <= (dst_ip, dport):
            return (src_ip, dst_ip, sport, dport, proto)
        return (dst_ip, src_ip, dport, sport, proto)

    def ingest(self, src_ip, dst_ip, sport, dport, proto, size, ts=None):
        """
        Record one packet. Returns None unless this packet is the n_packets-th
        packet of its flow, in which case it returns
        (flow_key, flow_record, sizes, directions, piat_ms_list).
        """
        ts = time.time() if ts is None else ts
        key = self.flow_key(src_ip, dst_ip, sport, dport, proto)
        flow = self.flows.get(key)
        if flow is None:
            flow = {
                "orig_src": src_ip,
                "orig_dst": dst_ip,
                "orig_sport": sport,
                "orig_dport": dport,
                "proto": proto,
                "packets": [],  # list of (size, direction, piat_ms)
                "last_packet_ts": None,
                "classified": False,
                "last_seen": ts,
            }
            self.flows[key] = flow

        self._packets_seen += 1
        if self._packets_seen % 500 == 0:
            self.purge_expired(ts)

        if flow["classified"]:
            flow["last_seen"] = ts
            return None

        direction = 0 if (src_ip, sport) == (flow["orig_src"], flow["orig_sport"]) else 1
        piat_ms = max(0.0, (ts - flow["last_packet_ts"]) * 1000.0) if flow["last_packet_ts"] is not None else 0.0
        flow["packets"].append((size, direction, piat_ms))
        flow["last_packet_ts"] = ts
        flow["last_seen"] = ts

        if len(flow["packets"]) < self.n_packets:
            return None

        flow["classified"] = True
        window = flow["packets"][: self.n_packets]
        sizes = [p[0] for p in window]
        directions = [p[1] for p in window]
        piats = [p[2] for p in window]
        return key, flow, sizes, directions, piats

    def purge_expired(self, now):
        expired = [k for k, f in self.flows.items() if now - f["last_seen"] > self.flow_timeout]
        for k in expired:
            del self.flows[k]
        return len(expired)
