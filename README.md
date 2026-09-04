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
  paper/                    Phase 4: main.tex (standalone paper) + Lab/ (the same content in the
                               university Lab-report format, main_lab.tex) + references.bib
  models/                   trained model metadata + metrics (the model .pkl itself is gitignored, see below)
  experiments/              ablation studies: hyperparameters/feature-window (ablation_study.py), real
                               per-window wait time (decision_delay_study.py), QoS class granularity
                               (class_granularity_study.py), synthetic-generator comparison
                               (synthetic_generator_comparison.py), external dataset validation
                               (cesnet_external_eval.py), plus a per-window compute-latency benchmark
                               (latency_study.py, superseded in the paper by decision_delay_study.py's
                               real wait-time numbers but kept for reference), with real results JSON
                               and requirements-experiments.txt for the two new scripts' extra deps

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
compiling to the 11-page `main.pdf` (10 pages of content, 1 of
references). The same content also exists as `Lab/*.tex` +
`main_lab.tex`, split into per-section files in the ACM format required
for the university Lab-report submission, compiling to `main_lab.pdf`.

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
- **Design choices are tested, not guessed**: a systematic
  one-factor-at-a-time sweep (22 independently retrained models,
  `experiments/ablation_study.py`) checks the 10-packet feature window and
  the deployed Random Forest's hyperparameters against the alternatives.
  15 packets measurably beats 10 on accuracy (0.896 vs. 0.871) but costs
  flow coverage and decision latency, which is why 10 stays the default;
  a 50-tree variant matches the deployed model's accuracy at half the size.
- **How much real time does 10 vs. 15 packets actually cost?** `experiments/decision_delay_study.py`
  sums real measured inter-arrival times (not a simulated packet rate)
  to compute how long a router really waits for `n_packets` to arrive.
  For Delay-Sensitive traffic, the median flow is classifiable in 43 ms
  at 10 packets versus 88 ms at 15, roughly double, for only 2.5 points
  of extra macro F1. That's the concrete cost behind "why 10 not 15."
- **Why 4 QoS classes, not more or fewer**: the granularity matches WMM's
  four 802.11e Access Categories, and a separate sweep
  (`experiments/class_granularity_study.py`) shows macro F1 falls
  monotonically as the taxonomy gets finer (0.904 at 2 classes, 0.843 at
  6). Splitting Delay-Sensitive further into gaming/VoIP/network-control
  costs accuracy without giving the router anything it could act on
  differently, which is why we stopped at 4.
- **No synthetic traffic generator resembles a real handshake**:
  `experiments/synthetic_generator_comparison.py` compares D-ITG, MGEN,
  and `iperf3` against real traffic on first-10-packet size variance.
  D-ITG and MGEN, given the identical profile, are structurally
  identical (variance = 0) and both get misclassified the same way.
  `iperf3`'s TCP handshake gets numerically closer to real traffic's
  variance, but it's still the wrong shape (generic TCP setup, not a TLS
  handshake) and still gets misclassified. None of the three operates
  above the transport layer, so none can be tuned into looking real.
- **Cross-network generalization is a real, disclosed limitation**:
  evaluating the unchanged, unretrained deployed model on
  [CESNET-TLS22](https://www.liberouter.org/technology-v2/tools-services-datasets/datasets/cesnet-tls22/),
  a real dataset from a different network
  (`experiments/cesnet_external_eval.py`), drops macro F1 from 0.871 to
  0.208. Web-Browsing (the majority class) is still recognized well; the
  other three collapse. We report this honestly as a boundary on what
  the headline 0.871 actually claims, not something to hide.

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
