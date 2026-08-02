# Client/server node image: generates and receives D-ITG synthetic traffic,
# real-pcap replay (tcpreplay/tcprewrite), and iperf3 bandwidth tests for the
# 4 QoS-class scenarios.
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        d-itg \
        tcpreplay \
        iperf3 \
        iproute2 \
        iputils-ping \
        python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ditg_scenarios.py /app/ditg_scenarios.py
