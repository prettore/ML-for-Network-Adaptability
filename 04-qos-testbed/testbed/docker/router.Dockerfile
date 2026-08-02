# Router node image: runs the Phase 2 sniffer (common/ + router/) with the
# trained QoS model, plus the tc/iptables tools it drives.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        iproute2 \
        iptables \
        tcpdump \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        pandas==2.2.2 \
        numpy==2.0.2 \
        scikit-learn==1.6.1 \
        lightgbm==4.6.0 \
        scapy>=2.5.0

WORKDIR /app
COPY common/ /app/common/
COPY router/ /app/router/
COPY models/ /app/models/

# No ENTRYPOINT/CMD here on purpose: Containernet starts this container with
# dcmd="sleep infinity" (see testbed/topology.py) and run_experiment.py
# launches `python3 router/sniffer.py ...` inside it afterwards via
# router.cmd(...). NET_ADMIN/NET_RAW are granted at container-creation time
# (topology.py's cap_add=["net_admin", "net_raw"]), not here.
