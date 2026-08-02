"""
Shared SPLT (Sequence of Packet Lengths and Times) feature extraction.

Imported by both the offline training script (phase1_train.py) and the
Phase 2 real-time router sniffer, so the exact same feature vector is
produced whether a flow comes from a Parquet column or is assembled live
packet-by-packet -- avoiding train/serve skew.

Feature vector layout (2 * n_packets floats): for each of the first
`n_packets` packets of the flow,
  - signed packet size: +size for src2dst, -size for dst2src (direction is
    folded into the sign instead of being a separate column), and
  - inter-arrival time in ms (0 for the first packet).
"""

import ast

import numpy as np

N_PACKETS_DEFAULT = 10


def _parse_list(value):
    if isinstance(value, str):
        return ast.literal_eval(value)
    if isinstance(value, (list, tuple, np.ndarray)):
        return list(value)
    return []


def extract_splt_features(splt_ps, splt_direction, splt_piat_ms, n_packets=N_PACKETS_DEFAULT):
    """Build a fixed-length (2 * n_packets,) feature vector from one flow's SPLT sequence."""
    ps = _parse_list(splt_ps)[:n_packets]
    direction = _parse_list(splt_direction)[:n_packets]
    piat = _parse_list(splt_piat_ms)[:n_packets]

    signed_ps = np.zeros(n_packets, dtype=np.float32)
    iat = np.zeros(n_packets, dtype=np.float32)

    for i in range(min(len(ps), n_packets)):
        if ps[i] == -1:
            signed_ps[i] = -1.0  # NFStream padding sentinel for flows shorter than n_packets
        else:
            sign = -1.0 if i < len(direction) and direction[i] == 1 else 1.0
            signed_ps[i] = sign * ps[i]
        iat[i] = piat[i] if i < len(piat) and piat[i] != -1 else 0.0

    return np.concatenate([signed_ps, iat])


def feature_names(n_packets=N_PACKETS_DEFAULT):
    return [f"ps_{i + 1}" for i in range(n_packets)] + [f"iat_{i + 1}" for i in range(n_packets)]


def build_feature_matrix(df, n_packets=N_PACKETS_DEFAULT):
    """Vectorized-ish builder: df must have splt_ps/splt_direction/splt_piat_ms columns."""
    rows = [
        extract_splt_features(ps, direction, piat, n_packets)
        for ps, direction, piat in zip(df["splt_ps"], df["splt_direction"], df["splt_piat_ms"])
    ]
    return np.vstack(rows)
