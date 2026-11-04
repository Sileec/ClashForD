#!/usr/bin/env python3
"""Build Threads_Domain.mrs from blackmatrix7 + local additions.

Threads-only adaptation of kiki's scripts/sync-services.py
(which builds Pixiv/LinkedIn/Threads). Only Threads is kept here.

Upstream: blackmatrix7/ios_rule_script -> rule/Clash/Threads/Threads.yaml
Local additions (ADDITIONS) are merged in, because the upstream
currently only carries DOMAIN-SUFFIX,threads.net (1 domain, 2024-01-08).

Usage: python3 scripts/sync-threads.py <mihomo-bin> <output-dir>
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

UPSTREAM = (
    "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/"
    "master/rule/Clash/Threads/Threads.yaml"
)

# Threads-specific domains the upstream does not cover.
# "+." prefix = mihomo domain text format (DOMAIN-SUFFIX).
ADDITIONS = [
    "+.threads.com",
    "+.threads.net",
    "+.threadsusercontent.com",
]

MAX_UPSTREAM_SIZE = 1 * 1024 * 1024


def upstream_domains():
    import yaml

    with urlopen(UPSTREAM, timeout=60) as resp:
        source = resp.read(MAX_UPSTREAM_SIZE + 1)
    if len(source) > MAX_UPSTREAM_SIZE:
        raise ValueError("upstream too large")
    parsed = yaml.safe_load(source)
    payload = parsed.get("payload") if isinstance(parsed, dict) else None
    if not isinstance(payload, list):
        raise ValueError("upstream payload is not a list")

    result = set()
    for entry in payload:
        if not isinstance(entry, str) or "," not in entry:
            continue
        kind, domain = (p.strip() for p in entry.split(",", 1))
        if kind == "DOMAIN-SUFFIX":
            result.add("+." + domain)
        elif kind == "DOMAIN":
            result.add(domain)
        # only DOMAIN / DOMAIN-SUFFIX are allowed; anything else is rejected
    if not result:
        raise ValueError("no usable domains in upstream")
    return result


def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <mihomo-bin> <output-dir>", file=sys.stderr)
        sys.exit(2)
    binary, outdir = sys.argv[1], Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    entries = sorted(upstream_domains() | set(ADDITIONS))
    print(f"Threads: {len(entries)} domains (upstream + local additions)")

    with tempfile.TemporaryDirectory() as tmp:
        yaml_path = Path(tmp) / "Threads_Domain.yaml"
        mrs_path = outdir / "Threads_Domain.mrs"
        yaml_path.write_text(
            f"# Source: {UPSTREAM}\n"
            "# Local additions: scripts/sync-threads.py ADDITIONS\n"
            "payload:\n" + "".join(f"  - {d}\n" for d in entries),
            encoding="utf-8",
        )
        subprocess.run(
            [binary, "convert-ruleset", "domain", "yaml",
             str(yaml_path), str(mrs_path)],
            check=True,
        )
        if not mrs_path.exists() or mrs_path.stat().st_size == 0:
            raise ValueError("converter produced no output")
    print(f"Threads: wrote {mrs_path} ({mrs_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
