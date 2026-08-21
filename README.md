# ML-Driven Early QoS Classification and Real-Time Enforcement for Encrypted Network Traffic

An end-to-end system that classifies network flows into 4 QoS classes from
just their first 10 packets, and uses that classification to actively drive
Linux traffic control (`tc`) and `iptables` on a router in real time —
built on top of, and extending, the [ML Flow Class Tutorial](https://github.com/FlowFrontiers/ml-flow-class-tutorial) notebooks.

## What this is

Modern traffic is almost entirely encrypted, so a router can no longer look
inside packets to decide "this is a video call, prioritize it" or "this is a
bulk download, it can wait." This project shows that a router doesn't need
to: the *pattern* of the first 10 packets (their sizes and timing) is enough
to tell the difference, and that classification can be turned into an
actual scheduling decision in real time — not just a research metric.

The 4 QoS classes: **Delay-Sensitive** (VoIP, gaming, DNS/control-plane),
**Video-Streaming** (video/audio streaming), **Bulk-Download** (large file
transfers, game/software updates), **Web-Browsing** (everything else,
best-effort).

### Headline results (real, measured — see the paper for full methodology)

| Metric | Result |
|---|---|
| Classification macro F1 (429,597 real flows, held-out test set) | **0.871** (accuracy 90.8%) |
| Deployed model size (depth-bounded, router-practical) | **236 MB** (down from 1.3 GB unbounded) |
| Router processing latency per flow (feature + predict + enforce) | **28.9 ms** average |
| Delay-Sensitive traffic delay, QoS off → on (5 Mbit/s bottleneck) | **1,532.8 ms → 0.095 ms** |
| Web-Browsing traffic delay, QoS off → on | **2,590.8 ms → 0.144 ms** |

## Repository structure

```
04-qos-testbed/          <- the QoS system (start here)
  common/                   feature extraction + QoS taxonomy, shared by training and the live sniffer
  phase1_train.py           Phase 1: dataset prep + model training
  router/                   Phase 2: real-time sniffer + tc/iptables enforcement
  testbed/                  Phase 3: Containernet topology, D-ITG traffic profiles, evaluation
  paper/                    Phase 4: the LaTeX paper (main.tex, references.bib, main.pdf)
  models/                   trained model metadata + metrics (the model .pkl itself is gitignored, see below)
  experiments/              ablation studies: hyperparameters/feature-window (ablation_study.py) + QoS class granularity (class_granularity_study.py), with real results JSON

01-data-collection/      <- tutorial: NFStream flow metering, SPLT, nDPI labeling
02-app-classification/   <- tutorial: data preparation + comparative ML modeling
03-explainability/       <- tutorial: XAI (SHAP, LIME) for traffic classifiers
```

## The 4 phases

**Phase 1 — Data & Model** (`04-qos-testbed/phase1_train.py`): maps 337 raw
nDPI application labels onto the 4 QoS classes (`common/qos_mapping.py`),
extracts SPLT features from the first 10 packets of each flow
(`common/splt_features.py`), and trains a Random Forest classifier with a
client-IP-disjoint train/test split to avoid data leakage.
```bash
cd 04-qos-testbed && pip install -r requirements-phase1.txt
python3 phase1_train.py   # fetches data.parquet automatically if missing
```

**Phase 2 — Router Sniffer** (`04-qos-testbed/router/`): a live sniffer
(`sniffer.py`) that watches traffic, classifies each flow the moment its
10th packet arrives using the *same* feature code as training
(`flow_tracker.py`), and installs `tc`/`iptables` rules
(`tc_manager.py`) to give it the matching QoS treatment.
```bash
sudo python3 router/sniffer.py --iface eth0            # live enforcement
sudo python3 router/sniffer.py --iface eth0 --dry-run   # preview commands only
```

**Phase 3 — Testbed** (`04-qos-testbed/testbed/`): a Containernet topology
(`topology.py`) plus D-ITG traffic profiles (`ditg_scenarios.py`) for each
QoS class, an experiment orchestrator (`run_experiment.py`), and an
evaluation harness (`evaluate.py`). Running the full topology needs
Containernet installed with root; `testbed/results/pilot/` contains the raw
logs from a real (topologically simplified, root-not-required) Docker pilot
run instead.

**Phase 4 — Paper** (`04-qos-testbed/paper/`): `main.tex` + `references.bib`,
compiling to the 6-page `main.pdf` linked above.

## Notable findings

- **Model size vs. accuracy**: an unconstrained Random Forest reaches 0.886
  macro F1 but pickles to 1.3 GB — impractical for a router. Bounding tree
  depth trades 0.015 F1 for a 236 MB model.
- **QoS trade-offs are real, and reported honestly**: giving Delay-Sensitive
  and Web-Browsing near-total priority means Video-Streaming and
  Bulk-Download absorb more congestion under enforcement than they did in
  the undifferentiated baseline — that's the QoS mechanism working as
  designed, not a bug, and the paper reports the costs alongside the wins.
- **A negative result worth knowing**: D-ITG's synthetic traffic doesn't
  reproduce a real TLS/QUIC handshake's packet-timing signature, so the live
  classifier mostly defaults synthetic flows to the majority class. The
  paper documents this and uses a ground-truth-label control to separately
  validate the enforcement mechanism from the classifier (which is
  independently validated on real traffic).

## Tutorial foundation (01–03)

`01-data-collection/`, `02-app-classification/`, and `03-explainability/`
are the original tutorial notebooks this project builds on and extends,
covering NFStream-based flow metering, iterative data preparation,
comparative modeling (Random Forest vs. LightGBM vs. others), and
explainable AI for traffic classifiers. They're self-contained — each
notebook fetches its own data and dependencies on first run. See their
inline documentation for details.

## Citation

If you use the underlying tutorial dataset or notebooks, please cite:

```bibtex
@unpublished{pekar2025tutorial,
  author = {Adrián Pekár, Richard Plný, and Karel Hynek},
  title  = {Tutorial on Network Traffic Flow Classification Using Machine Learning},
  note   = {Submitted for publication},
  year   = {2025}
}
```

See `04-qos-testbed/paper/references.bib` for the full bibliography of the
QoS system paper itself.
