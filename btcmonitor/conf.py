from pathlib import Path

# bitcoin.conf section name for each --network choice
NETWORK_SECTIONS = {
    "mainnet": "main",
    "testnet": "test",
    "testnet3": "test",
    "testnet4": "testnet4",
    "signet": "signet",
    "regtest": "regtest",
}

# Options Bitcoin Core ignores at the top level of bitcoin.conf unless the network is mainnet
NETWORK_ONLY_OPTIONS = {"rpcport"}


def read_bitcoin_conf(path: Path, network: str) -> dict[str, str]:
    """Return the bitcoin.conf settings that apply to `network`.

    Follows Bitcoin Core's rules: `[section]` blocks and `section.option=` prefixes target one
    network, top-level options apply to every network except network-only options such as
    rpcport, and a network-specific value wins over a top-level one. Missing or unreadable
    files yield no settings.
    """
    try:
        lines = Path(path).read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return {}

    wanted = NETWORK_SECTIONS.get(network, "main")
    top: dict[str, str] = {}
    scoped: dict[str, str] = {}
    section = ""
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        key_section = section
        if "." in key:
            key_section, key = key.split(".", 1)
        if not key_section:
            top.setdefault(key, value)  # Bitcoin Core uses the first value of a single-value option
        elif key_section == wanted:
            scoped.setdefault(key, value)

    settings = {k: v for k, v in top.items() if wanted == "main" or k not in NETWORK_ONLY_OPTIONS}
    settings.update(scoped)
    return settings
