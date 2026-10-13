"""Text formatting helpers for the panels"""


def format_bytes(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.0f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def format_txid(txid: str) -> str:
    """Format transaction ID as first4...last4"""
    if len(txid) >= 8:
        return f"{txid[:4]}...{txid[-4:]}"
    return txid


def format_time_since_block(seconds: int) -> str:
    """Format seconds into minutes:seconds format"""
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02d}"
