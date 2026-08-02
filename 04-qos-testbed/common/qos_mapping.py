"""
Maps NFStream/nDPI application labels onto the 4-class QoS taxonomy used
throughout this testbed: Delay-Sensitive, Video-Streaming, Bulk-Download,
Web-Browsing.

Mapping strategy (derived empirically from data/data.parquet, 429,597 flows
after the 02a-data-preparation cleaning pipeline):

1. `application_category_name` (nDPI's own coarse category) is used as the
   primary signal. It already separates most traffic sensibly, e.g. Media/
   Video/Streaming/Music -> streaming, Collaborative/VoIP/RemoteAccess ->
   interactive, SoftwareUpdate/Download/Cloud -> bulk transfer.
2. A small set of `application_name` overrides corrects the handful of
   cases where the category is empirically wrong for QoS purposes in this
   dataset: game-platform clients (Steam/EpicGames/Blizzard/EA) are tagged
   category "Game" but are dominated by large client/patch downloads, and
   TikTok/Facebook-Reels are tagged "SocialNetwork" but carry continuous
   short-form video. Overrides are checked first and win.
3. Anything not covered by either falls back to Web-Browsing, the
   best-effort default.
"""

QOS_CLASSES = ["Bulk-Download", "Delay-Sensitive", "Video-Streaming", "Web-Browsing"]

DEFAULT_CLASS = "Web-Browsing"

# application_name is nDPI's "Protocol.Service" naming (e.g. "TLS.Steam");
# keys here are the lowercased service part (text after the last '.', or the
# whole name when there is no '.').
SERVICE_OVERRIDES = {
    "steam": "Bulk-Download",  # TLS/HTTP.Steam -> category "Game", but traffic is dominated by game/client downloads
    "epicgames": "Bulk-Download",  # TLS/QUIC/DTLS.EpicGames -> category "Game", same reasoning
    "blizzard": "Bulk-Download",  # TLS/HTTP/QUIC.Blizzard (Battle.net) -> category "Game", patch/client downloads
    "electronicarts": "Bulk-Download",  # TLS.ElectronicArts (EA app) -> category "Game", patch/client downloads
    "tiktok": "Video-Streaming",  # TLS/QUIC.TikTok -> category "SocialNetwork", but content is short-form video
    "fbookreelstory": "Video-Streaming",  # Facebook/Instagram Reels -> category "SocialNetwork", video content
}

# nDPI application_category_name -> QoS class, covering every category
# observed in data.parquet after cleaning.
CATEGORY_MAP = {
    # Delay-Sensitive: interactive, real-time, or control-plane traffic
    "VoIP": "Delay-Sensitive",
    "Chat": "Delay-Sensitive",
    "Collaborative": "Delay-Sensitive",  # Zoom/Teams/Discord/Slack-style conferencing
    "RemoteAccess": "Delay-Sensitive",  # RDP, SSH
    "Network": "Delay-Sensitive",  # DNS, SNMP, STUN, LLMNR, DoH/DoT, mDNS - latency-critical control plane
    "ConnCheck": "Delay-Sensitive",  # captive-portal / connectivity probing
    "Game": "Delay-Sensitive",  # live multiplayer/cloud-gaming traffic (see SERVICE_OVERRIDES for exceptions)
    "Database": "Delay-Sensitive",  # interactive query round-trips
    "VirtAssistant": "Delay-Sensitive",  # e.g. Siri
    "RPC": "Delay-Sensitive",
    # Video-Streaming: continuous, buffered audio/video delivery
    "Media": "Video-Streaming",
    "Video": "Video-Streaming",
    "Streaming": "Video-Streaming",
    "Music": "Video-Streaming",  # audio streaming grouped with video: same sustained-throughput profile
    # Bulk-Download: large, throughput-bound, delay-tolerant transfers
    "SoftwareUpdate": "Bulk-Download",
    "Download": "Bulk-Download",  # includes BitTorrent, which nDPI files under "Download" rather than "P2P"
    "Cloud": "Bulk-Download",  # cloud storage sync/backup (OneDrive, Dropbox, AWS, Azure)
    # Web-Browsing: best-effort traffic and everything else
    "Web": "Web-Browsing",
    "SocialNetwork": "Web-Browsing",
    "Advertisement": "Web-Browsing",
    "Email": "Web-Browsing",
    "VPN": "Web-Browsing",  # tunnel carries arbitrary inner traffic; cannot disambiguate from the outer flow
    "Cybersecurity": "Web-Browsing",
    "System": "Web-Browsing",
    "AdultContent": "Web-Browsing",
    "ArtifIntelligence": "Web-Browsing",  # LLM chat/API request-response traffic
    "Shopping": "Web-Browsing",
    "DataTransfer": "Web-Browsing",  # observed apps here are small telemetry (CheckMK, Crashlytics), not bulk
}


def map_to_qos_class(application_name, application_category_name, unmapped_categories=None):
    """
    Map one flow's nDPI labels to a QoS class.

    `unmapped_categories`, if given a set, gets any application_category_name
    that fell through to DEFAULT_CLASS without an explicit entry in
    CATEGORY_MAP -- inspect it after a full pass to catch nDPI categories
    that weren't present when this taxonomy was built.
    """
    service = str(application_name).split(".")[-1].strip().lower() if application_name else ""
    if service in SERVICE_OVERRIDES:
        return SERVICE_OVERRIDES[service]

    category = str(application_category_name).strip() if application_category_name else ""
    if category in CATEGORY_MAP:
        return CATEGORY_MAP[category]

    if unmapped_categories is not None:
        unmapped_categories.add(category)
    return DEFAULT_CLASS
