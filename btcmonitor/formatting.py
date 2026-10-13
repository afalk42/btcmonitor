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
    """Format seconds as minutes:seconds, or as a duration from an hour up (e.g. during initial sync)"""
    if seconds >= 3600:
        return format_duration(seconds)
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02d}"


def format_age(seconds: float) -> str:
    """Compact age of a block: "<1m", "12m", then as format_duration from an hour up"""
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{int(seconds) // 60}m"
    return format_duration(seconds)


def format_duration(seconds: float) -> str:
    """Rough human duration with the two largest units, e.g. "2d 3h", "4h 05m", "12m 30s", "45s\""""
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


# Symbols written before the amount; other currencies get their code after it ("1,234 SEK")
CURRENCY_SYMBOLS = {
    "usd": "$",
    "eur": "€",
    "gbp": "£",
    "jpy": "¥",
    "cny": "¥",
    "inr": "₹",
    "krw": "₩",
    "brl": "R$",
    "cad": "C$",
    "aud": "A$",
}


def format_fiat(amount: float, currency: str, decimals: int = 0) -> str:
    number = f"{amount:,.{decimals}f}"
    symbol = CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}{number}" if symbol else f"{number} {currency.upper()}"


def fiat_label(currency: str) -> str:
    """Column heading for amounts in `currency`, e.g. "US$" or "EUR\""""
    return "US$" if currency == "usd" else currency.upper()
