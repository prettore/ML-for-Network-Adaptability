# NFStream Documentation

This document provides a comprehensive description of all 91 columns in NFStream CSV files based on analysis of the NFStream source code and nDPI integration.

## Overview

NFStream generates CSV files with 91 columns containing network flow analysis data. The columns are organized into several categories: flow identifiers, timing metrics, statistical features, TCP flags, Sub-Packet Length and Time (SPLT) features, and application layer information derived from Deep Packet Inspection (DPI).

## Column Descriptions

### Flow Identifiers (Columns 1-14)
Basic flow identification and network layer information:

1.  **id** - A unique, sequential identifier for each flow, starting from 0.
2.  **expiration_id** - Flow expiration reason identifier. Possible values:
    - `0`: Idle timeout expiration.
    - `1`: Active timeout expiration.
    - `-1`: Custom plugin-forced expiration (e.g., due to FIN/RST packets).
3.  **src_ip** - Source IP address (string format).
4.  **src_mac** - Source MAC address (string format).
5.  **src_oui** - Source Organizationally Unique Identifier (first 3 bytes of MAC).
6.  **src_port** - Source port number.
7.  **dst_ip** - Destination IP address (string format).
8.  **dst_mac** - Destination MAC address (string format).
9.  **dst_oui** - Destination Organizationally Unique Identifier.
10. **dst_port** - Destination port number.
11. **protocol** - IP protocol number. Currently supported:
   - `1`: ICMP
   - `6`: TCP
   - `17`: UDP
   - `58`: ICMPv6
12. **ip_version** - IP version (4 or 6).
13. **vlan_id** - VLAN identifier (if present).
14. **tunnel_id** - Tunnel identifier (if tunnel decoding is enabled).
    - `0`: No Tunnel
    - `1`: GTP
    - `2`: CAPWAP
    - `3`: TZSP

### Flow Summary Metrics (Columns 15-29)
Flow timing, packet, and byte count metrics:

**Bidirectional Metrics:**
15. **bidirectional_first_seen_ms** - Timestamp of first packet in flow (milliseconds).
16. **bidirectional_last_seen_ms** - Timestamp of last packet in flow (milliseconds).
17. **bidirectional_duration_ms** - Total flow duration (milliseconds).
18. **bidirectional_packets** - Total number of packets in both directions.
19. **bidirectional_bytes** - Total bytes in both directions.

**Source to Destination Metrics:**
20. **src2dst_first_seen_ms** - Timestamp of first src→dst packet.
21. **src2dst_last_seen_ms** - Timestamp of last src→dst packet.
22. **src2dst_duration_ms** - Duration of src→dst traffic.
23. **src2dst_packets** - Number of packets from source to destination.
24. **src2dst_bytes** - Total bytes from source to destination.

**Destination to Source Metrics:**
25. **dst2src_first_seen_ms** - Timestamp of first dst→src packet.
26. **dst2src_last_seen_ms** - Timestamp of last dst→src packet.
27. **dst2src_duration_ms** - Duration of dst→src traffic.
28. **dst2src_packets** - Number of packets from destination to source.
29. **dst2src_bytes** - Total bytes from destination to source.

### Flow Statistics (Columns 30-77)
- Flow statistics include:
    - Statistical analysis of packet sizes and packet-inter arrival times across different directions.
    - Counts of TCP flags observed in the flow.
- Statistical features are only computed when the `statistical_analysis` (disabled by default) parameter is enabled.
- Standard deviation calculations use an online algorithm equivalent to the sample standard deviation.

#### Packet Size Statistics (Columns 30-41)
Statistical analysis of packet sizes across different directions.

**Bidirectional Statistics:**
30. **bidirectional_min_ps** - Minimum packet size (bidirectional).
31. **bidirectional_mean_ps** - Mean packet size (bidirectional).
32. **bidirectional_stddev_ps** - Standard deviation of packet sizes (bidirectional).
33. **bidirectional_max_ps** - Maximum packet size (bidirectional).

**Source to Destination Statistics:**
34. **src2dst_min_ps** - Minimum packet size (src→dst).
35. **src2dst_mean_ps** - Mean packet size (src→dst).
36. **src2dst_stddev_ps** - Standard deviation of packet sizes (src→dst).
37. **src2dst_max_ps** - Maximum packet size (src→dst).

**Destination to Source Statistics:**
38. **dst2src_min_ps** - Minimum packet size (dst→src).
39. **dst2src_mean_ps** - Mean packet size (dst→src).
40. **dst2src_stddev_ps** - Standard deviation of packet sizes (dst→src).
41. **dst2src_max_ps** - Maximum packet size (dst→src).

#### Packet Inter-Arrival Time (PIAT) Statistics (Columns 42-53)
Statistical analysis of time intervals between consecutive packets.

**Bidirectional PIAT:**
42. **bidirectional_min_piat_ms** - Minimum inter-arrival time (bidirectional).
43. **bidirectional_mean_piat_ms** - Mean inter-arrival time (bidirectional).
44. **bidirectional_stddev_piat_ms** - Standard deviation of inter-arrival times (bidirectional).
45. **bidirectional_max_piat_ms** - Maximum inter-arrival time (bidirectional).

**Source to Destination PIAT:**
46. **src2dst_min_piat_ms** - Minimum inter-arrival time (src→dst).
47. **src2dst_mean_piat_ms** - Mean inter-arrival time (src→dst).
48. **src2dst_stddev_piat_ms** - Standard deviation of inter-arrival times (src→dst).
49. **src2dst_max_piat_ms** - Maximum inter-arrival time (src→dst).

**Destination to Source PIAT:**
50. **dst2src_min_piat_ms** - Minimum inter-arrival time (dst→src).
51. **dst2src_mean_piat_ms** - Mean inter-arrival time (dst→src).
52. **dst2src_stddev_piat_ms** - Standard deviation of inter-arrival times (dst→src).
53. **dst2src_max_piat_ms** - Maximum inter-arrival time (dst→src).

#### TCP Flags (Columns 54-77)
Counts of TCP flags observed in the flow.

**Bidirectional TCP Flags:**
54. **bidirectional_syn_packets** - Count of SYN flag packets (bidirectional).
55. **bidirectional_cwr_packets** - Count of CWR (Congestion Window Reduced) flag packets.
56. **bidirectional_ece_packets** - Count of ECE (ECN Echo) flag packets.
57. **bidirectional_urg_packets** - Count of URG (Urgent) flag packets.
58. **bidirectional_ack_packets** - Count of ACK flag packets.
59. **bidirectional_psh_packets** - Count of PSH (Push) flag packets.
60. **bidirectional_rst_packets** - Count of RST (Reset) flag packets.
61. **bidirectional_fin_packets** - Count of FIN flag packets.

**Source to Destination TCP Flags:**
62. **src2dst_syn_packets** - Count of SYN flag packets (src→dst).
63. **src2dst_cwr_packets** - Count of CWR flag packets (src→dst).
64. **src2dst_ece_packets** - Count of ECE flag packets (src→dst).
65. **src2dst_urg_packets** - Count of URG flag packets (src→dst).
66. **src2dst_ack_packets** - Count of ACK flag packets (src→dst).
67. **src2dst_psh_packets** - Count of PSH flag packets (src→dst).
68. **src2dst_rst_packets** - Count of RST flag packets (src→dst).
69. **src2dst_fin_packets** - Count of FIN flag packets (src→dst).

**Destination to Source TCP Flags:**
70. **dst2src_syn_packets** - Count of SYN flag packets (dst→src).
71. **dst2src_cwr_packets** - Count of CWR flag packets (dst→src).
72. **dst2src_ece_packets** - Count of ECE flag packets (dst→src).
73. **dst2src_urg_packets** - Count of URG flag packets (dst→src).
74. **dst2src_ack_packets** - Count of ACK flag packets (dst→src).
75. **dst2src_psh_packets** - Count of PSH flag packets (dst→src).
76. **dst2src_rst_packets** - Count of RST flag packets (dst→src).
77. **dst2src_fin_packets** - Count of FIN flag packets (dst→src).

### Sub-Packet Length and Time (SPLT) Features (Columns 78-80)
Sequence of Packet Length and Time features capture the initial packets of a flow. 
The number of packets captured (N) is determined by the `splt_analysis=n` parameter when configuring NFStream.:

78. **splt_direction** - List of packet directions (0=src2dst, 1=dst2src, -1=no packet).
79. **splt_ps** - List of first N packet sizes (sequence of packet lengths).
80. **splt_piat_ms** - List of first N packet inter-arrival times (sequence of timing).

### Application Layer Information (DPI) (Columns 81-89)
Deep Packet Inspection provided by nDPI library. 
All these features are provided by nDPI but copied into NFStream's flow structure.
Application layer information requires `n_dissections > 0` to activate nDPI processing.

81. **application_name** - Detected application/protocol name.
    <!-- - Provided by nDPI through `ndpi_protocol2name()` function. -->
    - The number of supported protocols is dependent on the nDPI library version.
    - Examples: "DNS", "TLS.Netflix", "STUN.WhatsApp", "HTTP.Facebook".

82. **application_category_name** - Application category.
    <!-- - Provided by nDPI through `ndpi_category_get_name()` function. -->
    - The number of categories is dependent on the nDPI library version.
    - Examples: "Web", "SocialNetwork", "VoIP", "Game", "Streaming", "VPN".

83. **application_is_guessed** - Boolean indicating if protocol detection was uncertain.
    - Set when detection is based on incomplete information or heuristics.
    - Triggered by `ndpi_detection_giveup()` when insufficient packets are available.

84. **application_confidence** - Confidence level of protocol detection (0-9):
    - `0`: NDPI_CONFIDENCE_UNKNOWN - Unknown classification.
    - `1`: NDPI_CONFIDENCE_MATCH_BY_PORT - Classification based only on L4 ports.
    - `2`: NDPI_CONFIDENCE_NBPF - PF_RING nBPF custom protocol.
    - `3`: NDPI_CONFIDENCE_DPI_PARTIAL - Based on partial/incomplete DPI information.
    - `4`: NDPI_CONFIDENCE_DPI_PARTIAL_CACHE - Based on LRU cache with partial DPI info.
    - `5`: NDPI_CONFIDENCE_DPI_CACHE - Based on LRU cache (session correlation).
    - `6`: NDPI_CONFIDENCE_DPI - Full deep packet inspection.
    - `7`: NDPI_CONFIDENCE_MATCH_BY_IP - Classification based only on IP addresses.
    - `8`: NDPI_CONFIDENCE_DPI_AGGRESSIVE - Aggressive DPI (possible false positive).
    - `9`: NDPI_CONFIDENCE_CUSTOM_RULE - Matching custom rules.

85. **requested_server_name** - Server identifier extracted from various protocols:
    - **TLS/QUIC/DTLS:** Server Name Indication (SNI) from Client Hello.
    - **HTTP:** Host header value.
    - **DNS:** Query name.
    - **Email protocols:** Server hostname.

86. **client_fingerprint** - Protocol-specific client fingerprints:
    - **TLS/QUIC:** JA3C fingerprint.
    - **SSH:** HASSH client fingerprint.
    - **DHCP:** Option request list fingerprint.
    - **Other protocols:** Empty.

87. **server_fingerprint** - Protocol-specific server fingerprints:
    - **TLS/QUIC:** JA3S fingerprint.
    - **SSH:** HASSH server fingerprint.
    - **DHCP:** Empty (no server-side DHCP fingerprint).
    - **Other protocols:** Empty.

88. **user_agent** - HTTP User-Agent header (when available).

89. **content_type** - HTTP Content-Type header (when available).

### System Visibility Features (Columns 90-91)
These additional columns are available when `system_visibility_mode = 1` (default is `0`). 
They are only available for live capture (not PCAP analysis).

90. **system_process_pid** - Process ID of the host process that generated the flow.
    - Type: int
    - Default value: -1 (when process cannot be identified).
    - Only available for live capture (not PCAP analysis).

91. **system_process_name** - Name of the host process that generated the flow.
    - Type: str
    - Default value: "" (empty string when process cannot be identified).
    - Examples: "chrome", "firefox", "spotify", "zoom".

## Configuration and Behavior

### Accounting Modes

<!-- NFStream supports different accounting modes that affect how packet sizes are calculated, impacting columns 30-41 and column 79:

- **Mode 0 (Default):** Link layer size - includes all headers and framing.
- **Mode 1:** IP layer size - from IP header onwards.
- **Mode 2:** Transport layer size - from TCP/UDP header onwards.
- **Mode 3:** Payload size - only the actual data payload. -->

### Accounting Modes

A fundamental challenge in network analysis is defining a "packet's size." Different tools and protocols handle this inconsistently (e.g., Wireshark may report TCP length as payload-only, while UDP length includes the UDP header). This ambiguity makes automated, cross-protocol analysis difficult and unreliable.

NFStream solves this problem by providing a **unified, layered abstraction** for packet sizing via its `accounting_mode` parameter. This ensures that a given "size" has the same unambiguous meaning regardless of the underlying protocol (TCP, UDP, ICMP) or IP version (IPv4, IPv6).

| Mode | Name              | Description                                                                 |
|:-----|:------------------|:----------------------------------------------------------------------------|
| 0    | **Link Layer**    | The full, raw frame size as seen on the wire, including all headers.        |
| 1    | **IP Layer**      | The IP packet size, from the IP header to the end of the payload.           |
| 2    | **Transport Layer**| The transport segment size, from the TCP/UDP header to the end of the payload. |
| 3    | **Payload**       | The application data (payload) size only, with all headers stripped.      |

#### How It Works: Predictable Header Stripping

The modes work by predictably stripping headers at each layer. This provides a consistent and logical progression:

-   **Mode 0 → 1:** Removes link-layer headers (e.g., 14 bytes for an Ethernet header).
-   **Mode 1 → 2:** Removes the IP header (e.g., 20 bytes for a standard IPv4 header, 40 bytes for IPv6).
-   **Mode 2 → 3:** Removes the transport-layer header (e.g., 8 bytes for UDP; 20+ bytes for TCP, depending on options).

This consistency allows practitioners to derive precise measurements with simple arithmetic:
-   **Application data only:** `mode3_size`
-   **RFC-compliant UDP size:** `mode2_size` (UDP header + data)
-   **Transport header size:** `mode2_size - mode3_size`
-   **Total L2-L4 overhead:** `mode0_size - mode3_size`

#### Consistency Across All Protocols

This unified model is intentionally designed to handle protocol nuances consistently, which is essential for automated analysis:

-   **IPv4 & IPv6:** The logic works identically for both IP versions, correctly accounting for the different header sizes (e.g., 20 bytes for IPv4 vs. 40 for IPv6).
-   **ICMP & ICMPv6:** Although technically network-layer protocols, NFStream treats the ICMP header as a "transport" layer for consistency. This means `mode2_size` includes the ICMP header, and `mode3_size` is the ICMP payload only, following the same logic as TCP/UDP.
<!-- -   **TCP:** Correctly handles the variable size of the TCP header based on its options. A SYN packet's header will be larger than a standard data packet's header, and this is accurately reflected. -->


### Deep Packet Inspection (DPI) Configuration

The `n_dissections` parameter controls nDPI behavior:

- **Value:** Maximum number of packets (0-255) that nDPI analyzes per flow.
- **n_dissections = 0:** No DPI, application fields remain empty.
- **n_dissections = 1:** Only first packet analyzed, then immediate guess attempt.
- **Higher values:** More accurate detection but higher computational cost.

**Detection Process:**
1. nDPI analyzes packets until protocol is detected or `n_dissections` limit reached.
2. If protocol remains unknown after limit, `ndpi_detection_giveup()` attempts heuristic classification.
3. Detection quality depends on having initial flow packets (especially handshakes).

### System Visibility Configuration

#### system_visibility_mode Parameter
- **0 (Default):** Disabled - no system visibility features.
- **1:** Process information - collects PID and process name for flows.

#### system_visibility_poll_ms Parameter
- Controls polling frequency for system process detection (default: 100ms).
- Lower values = more accurate detection, higher CPU usage.
- Higher values = less CPU usage, potentially missed short-lived connections.

## Key Concepts and Implementation Details

### Flow Identification

NFStream uses a 7-tuple for flow identification:

1.  **src_ip** (source IP address)
2.  **dst_ip** (destination IP address)
3.  **src_port** (source port)
4.  **dst_port** (destination port)
5.  **protocol** (IP protocol: TCP=6, UDP=17, etc.)
6.  **vlan_id** (VLAN identifier) (0 if no VLAN)
7.  **tunnel_id** (tunnel identifier when `decode_tunnels` is enabled) (0 if no tunnel) The `tunnel_id` is only included if `decode_tunnels` is enabled.

The flow key is bidirectional - the algorithm ensures consistent ordering regardless of packet direction by comparing IP addresses and ports.

### Parallel Processing and Determinism (`n_meters`)

NFStream is designed for high performance and can leverage multiple CPU cores for parallel packet processing. This behavior is controlled by the `n_meters` parameter.

-   **`n_meters=0` (Default, Auto-scaling):** NFStream automatically detects the number of available CPU cores and launches a corresponding number of parallel metering processes. This is the optimal setting for maximizing throughput in high-speed, live capture environments.
-   **`n_meters=1` (Single-threaded):** Forces all processing to occur on a single thread. This is the recommended setting for research, tutorials, and any scenario where **reproducibility is required**.
-   **`n_meters > 1` (Manual):** Manually specifies the number of parallel processes to use.

#### Flow Affinity and Packet Ordering

To ensure data integrity during parallel processing, NFStream guarantees **flow affinity**: all packets belonging to the same flow (as defined by its 7-tuple key) are **always** sent to the same metering process. This is achieved by hashing the flow's 7-tuple and using the result to select a worker (`hash % n_meters`).

This mechanism provides two critical guarantees:
1.  **No Duplicate Flows:** A flow is only ever present in one worker's cache.
2.  **Feature Consistency:** The calculated features (byte counts, statistics, etc.) for any given flow will be **absolutely identical** across multiple runs.
3.  **Packet Order Preservation:** The sequence of packets *within* a single flow is always preserved and processed in the correct order.

#### Deterministic Output Order

While the features of a flow are always consistent, the use of multiple threads means the **order in which different flows appear in the final output** (e.g., the row order in a CSV or DataFrame) can be non-deterministic between runs. This is due to minor variations in thread scheduling and processing speeds.

-   **For maximum performance:** Use `n_meters=0`. The flow records will be correct, but their row order might change slightly on each execution.
-   **For deterministic output order:** Use `n_meters=1`. This guarantees that the final CSV or DataFrame will be identical, row by row, every time the program is run on the same input.

It is also important to note that even with `n_meters=1`, the output flow order is **deterministic but not strictly chronological** by start time. The order is determined by when flows are expired, which is a function of both packet arrival times and periodic garbage collection of idle flows from an LRU (Least Recently Used) cache.

### Tunnel Decoding

The `decode_tunnels` parameter (enabled by default) allows NFStream to look inside supported tunneling protocols to identify the inner flow. When a tunnel is detected, the `tunnel_id` field is populated, and the inner packet's 5-tuple is used for flow identification.

**Supported Tunnels:**
1. **GTP-U** (GPRS Tunneling Protocol User Plane)
   - Port: 2152
   - Used in mobile networks (3G/4G/5G)
   
2. **CAPWAP** (Control and Provisioning of Wireless Access Points)
   - Port: 5247
   - Used in wireless network management
   
3. **TZSP** (TaZmen Sniffer Protocol)
   - Port: 37008
   - Used for remote packet capture

### Anonymization Method: Blake2b Hashing

NFStream's data anonymization feature is implemented using the **Blake2b** cryptographic hash function, provided by Python's standard `hashlib` library. Blake2b is a modern algorithm known for being extremely fast while providing a high level of security, making it ideal for high-throughput network analysis.

The anonymization process, triggered by the `columns_to_anonymize` parameter in export methods (e.g., `to_csv`, `to_pandas`), applies this hash to specified fields, typically IP and MAC addresses.

Key properties of this implementation include:

-   **Irreversible (One-Way):** The hash function is designed to be one-way, meaning the original IP or MAC address cannot be recovered from its anonymized hash.
-   **Consistent Within Export (Deterministic)**: Within a single export operation, the same input value (e.g., the IP address `192.168.1.1`) will **always** produce the exact same hash output. This is critical for analysis as it preserves network topology within that dataset; for example, you can still correctly count all flows originating from the same, now-anonymized, source.
-   **Secure with Random Keying:** The implementation uses a **randomly generated 64-byte secret key** for each export operation. This means the same IP address will produce different hashes across different exports, preventing linkage between separate data collections and enhancing privacy protection. The BLAKE2b algorithm generates a 64-byte (512-bit) digest, represented as a 128-character hexadecimal string, which is cryptographically strong and suitable for privacy-preserving data sharing.
-   **Export Isolation:** Each call to `to_pandas()` or `to_csv()` generates a fresh secret key, ensuring that anonymized data from different exports cannot be correlated, even if they contain the same original addresses. This protects against cross-dataset re-identification attacks.

### IP Fragmentation Handling

NFStream has limited support for IP fragmented packets, which affects both statistical accuracy and DPI analysis.

#### Handling Fragmented Packets

NFStream examines the 13-bit fragment offset field in the IP header:
- **First fragment (offset = 0):** Processed normally by both NFStream and nDPI.
- **Subsequent fragments (offset > 0):** Completely ignored and discarded.

#### Impact on Statistics and DPI

**NFStream Statistics (Columns 18-29, 30-53):**
- Packet counts, byte counts, timing metrics, and packet size statistics only reflect **first fragments**.
- Subsequent fragments are not counted in any statistics.
- This leads to underestimation of actual traffic volume for fragmented flows.

**Application Layer Detection (Columns 81-89):**
- Although nDPI internally supports fragment reassembly and management (e.g., DNS, DTLS certificates, and QUIC handshakes), NFStream passes only the **first fragment** for protocol analysis.
- Thus, no packet reassembly is performed - subsequent fragments are discarded in NFStream before reaching nDPI.
- This can result in:
  - Failed protocol detection for fragmented handshakes (flows may appear as "Unknown" applications).
  - Incomplete fingerprint extraction (e.g., TLS ClientHello spanning multiple fragments).
  - Reduced `application_confidence` values.
  - Increased reliance on `application_is_guessed` heuristics.
- **Context matters**:
  - **End-device capture**: OS typically reassembles fragments before libpcap, so this limitation rarely affects data quality.
  - **Network capture**: Fragments appear separately, affecting both statistics and protocol detection.

#### Real-World Implications

**When This Matters:**
1. **Large TLS/DTLS handshakes** that exceed MTU (common with certificate chains).
2. **DNS responses** larger than standard packet sizes.
3. **QUIC initial packets** with large client/server hello messages.
4. **High-throughput applications** that may fragment at IP layer.
5. **Network environments** with smaller MTU settings.

#### Recommendations for Analysis

When analyzing NFStream CSV data:
1. Be aware that packet/byte counts may be underestimated for fragmented traffic.
2. Low confidence values might indicate fragmentation issues, not just difficult-to-detect protocols.
3. Consider network MTU settings when interpreting application detection accuracy.
4. Fragmented flows might require additional analysis outside of NFStream.

### Timeout Handling

NFStream uses two types of timeouts to determine when flows should be expired and exported, implemented through both packet-triggered and periodic garbage collection mechanisms.

#### Timeout Types

**Idle Timeout (Default: 120 seconds)**
- Flow expires when no packets are observed for the specified duration.
- Logic: `(current_time - bidirectional_last_seen_ms) >= idle_timeout`
- Based on the time since the **last packet** in either direction.
- Ensures inactive flows don't consume memory indefinitely.

**Active Timeout (Default: 1800 seconds / 30 minutes)**
- Flow expires after existing for the specified duration regardless of activity.
- Logic: `(current_time - bidirectional_first_seen_ms) >= active_timeout`
- Based on the time since the **first packet** that created the flow.
- Prevents long-running flows from growing indefinitely large.

**Special Cases:**
- `idle_timeout=0`: Flows expire immediately after each packet (single-packet flows)
- `active_timeout=0`: Flows expire immediately after creation (single-packet flows)
- Very low values may impact performance due to frequent flow creation/destruction

#### Timeout Triggering Mechanisms

NFStream employs **dual timeout checking** for comprehensive flow management:

1.  **Packet-Triggered Expiration**
    - **When**: Every time a new packet arrives for an existing flow
    - **Process**: During flow update, NFStream checks if the flow should expire
    - **Critical Behavior**: When timeout is detected:
      1. **Old flow expires** immediately and gets exported to output
      2. **Same triggering packet** creates a **NEW flow** with fresh statistics
    - **Advantage**: Immediate expiration when activity resumes on an expired flow, ensuring no packet loss

2.  **Periodic Garbage Collection**
    - **Frequency**: Every 10 milliseconds (`meter_scan_interval = 10`).
    - **Function**: `meter_scan()` in `meter.py`.
    - **Budget**: Maximum 1000 flows checked per scan cycle (prevents CPU spikes).
    - **Order**: Flows checked in LRU (Least Recently Used) order for efficiency.
    - **Purpose**: Ensures flows expire even when no new packets arrive.

<!-- #### Workflow

1. Packet Arrives: A new packet is captured.
2. Flow Lookup: nfstream calculates the packet's 7-tuple key and finds the corresponding existing flow in its cache.
3. Timeout Check: The packet's timestamp is compared against the bidirectional_last_seen_ms of the existing flow (for idle_timeout) and the bidirectional_first_seen_ms (for active_timeout). The check determines that the flow has expired.
4. Flow Finalization & Export: The existing flow is finalized. Its duration, total bytes/packets, and other metrics are calculated based on the packets it has seen up to this point (not including the new packet). This completed flow record is then sent to be written out (e.g., to the CSV file).
5. Old Flow Deletion: The old, now-expired flow is deleted from the cache.
6. New Flow Creation: The packet that triggered the timeout is used as the very first packet of a brand new flow. This new flow is created and placed in the cache, occupying the same key as the one that was just removed. -->

#### Implementation Details

**Timeout Precision:**
- All timeouts converted to milliseconds internally.
- Time comparisons use millisecond precision for accuracy.

**Performance Considerations:**
- LRU cache structure enables efficient timeout checking.
- Scan budget prevents timeout checking from blocking packet processing.
- Most recently active flows are checked last (optimization for active networks).

<!-- ### Key Implementation Notes -->

<!-- - All fingerprints are provided by nDPI but copied into NFStream's flow structure. -->
<!-- - Fingerprint fields are protocol-specific and only populated for supported protocols. -->
<!-- - Standard deviation calculations use an online algorithm equivalent to the sample standard deviation. -->
<!-- - Statistical features are only computed when the `statistical_analysis` parameter is enabled. -->
<!-- - Application layer information requires `n_dissections > 0` to activate nDPI processing. -->
