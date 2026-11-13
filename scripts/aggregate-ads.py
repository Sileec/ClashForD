#!/usr/bin/env python3
"""Prototype: self-aggregate ad/privacy rule lists from upstream sources.

Replaces the blackmatrix7 dependency for AdvertisingLite and Privacy.
Sources (all verified live 2026-11-13):
  Privacy:        ACL4SSR BanEasyPrivacy.list + skk.moe reject-drop/no-drop.conf
  AdvertisingLite: ACL4SSR BanAD.list + BanEasyList.list + BanEasyListChina.list
                  (+ optional anti-AD anti-ad-domains.txt, --with-anti-ad)

Outputs (mihomo formats, same shape as the current BM7-derived files):
  <name>.yaml          classical yaml (all rule types)
  <name>_Domain.yaml   domain yaml (DOMAIN + DOMAIN-SUFFIX only, for MRS)

Design notes:
- Parsers handle Clash .list, Surge .conf (TYPE,value lines) and plain
  domain lists (anti-AD: one domain per line -> DOMAIN-SUFFIX).
- Junk dropped: skk.moe canary domain 7h15.ru1353t.1s.m4d3.by.5ukk4w.skk.moe
  (a deliberate test entry, not a real ad domain) and DOMAIN-SUFFIX,null.
- Dedup with suffix subsumption: if suffix .example.com exists, exact
  example.com and any *.example.com suffixes under it are redundant.
- filter-alibaba logic is applied to AdvertisingLite (drop *.alicdn.com
  except the 6 KEEP subdomains), same as the current pipeline.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

CANARY = "7h15.ru1353t.1s.m4d3.by.5ukk4w.skk.moe"

# Alibaba CDN: keep only known ad subdomains (same as filter-alibaba.py).
ALIBABA_KEEP = {
    "alimama.alicdn.com",
    "aecpm.alicdn.com",
    "afp.alicdn.com",
    "afpmm.alicdn.com",
    "atanx2.alicdn.com",
    "unidesk.alicdn.com",
}

DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD"}
IP_TYPES = {"IP-CIDR", "IP-CIDR6", "IP-ASN"}


def normalize_domain(value: str) -> str:
    value = value.strip().strip("'\"").lower().rstrip(".")
    if value.startswith("+."):
        value = value[2:]
    elif value.startswith("."):
        value = value[1:]
    return value


def parse_typed_file(path: Path):
    """Parse Clash .list / Surge .conf: TYPE,value lines. Yields (type, value)."""
    rules = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # Surge conf may carry trailing options after the value; keep first two fields.
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        rtype = parts[0].upper()
        value = parts[1]
        if rtype in DOMAIN_TYPES:
            value = normalize_domain(value)
            if not value or value == "null" or value == CANARY:
                continue
        elif rtype in IP_TYPES:
            value = value.strip()
            if not value:
                continue
        else:
            continue
        rules.append((rtype, value))
    return rules


def parse_plain_domains(path: Path):
    """Parse anti-AD style plain domain list: one domain per line -> SUFFIX."""
    rules = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        domain = normalize_domain(line)
        if not domain or domain == CANARY:
            continue
        rules.append(("DOMAIN-SUFFIX", domain))
    return rules


def dedup_subsumption(rules):
    """Dedup + suffix subsumption. Returns (domain_rules, other_rules).

    domain_rules: list of (type, value) with type in {DOMAIN, DOMAIN-SUFFIX},
    with exact entries covered by a suffix removed, and suffixes covered by
    a broader suffix removed.
    other_rules: KEYWORD / WILDCARD / IP rules, deduped only.
    """
    suffixes = set()
    exacts = set()
    others = set()
    for rtype, value in rules:
        if rtype == "DOMAIN-SUFFIX":
            suffixes.add(value)
        elif rtype == "DOMAIN":
            exacts.add(value)
        else:
            others.add((rtype, value))

    # A suffix is redundant if a broader suffix (one of its parent domains)
    # is also a suffix.
    def covered_by_suffix(domain: str) -> bool:
        labels = domain.split(".")
        for i in range(1, len(labels)):
            if ".".join(labels[i:]) in suffixes:
                return True
        return False

    kept_suffixes = {s for s in suffixes if not covered_by_suffix(s)}
    kept_exacts = {e for e in exacts if e not in kept_suffixes and not covered_by_suffix(e)}
    domain_rules = [("DOMAIN", e) for e in sorted(kept_exacts)]
    domain_rules += [("DOMAIN-SUFFIX", s) for s in sorted(kept_suffixes)]
    return domain_rules, sorted(others)


def apply_alibaba_filter(domain_rules, other_rules):
    """Drop *.alicdn.com except KEEP (AdvertisingLite only)."""
    def keep_domain(domain: str) -> bool:
        if domain == "alicdn.com" or domain.endswith(".alicdn.com"):
            return domain in ALIBABA_KEEP
        return True

    domain_rules = [(t, v) for t, v in domain_rules if keep_domain(v)]
    other_rules = [
        (t, v) for t, v in other_rules
        if t not in DOMAIN_TYPES or keep_domain(v)
    ]
    return domain_rules, other_rules


def write_classical(path: Path, name: str, sources, domain_rules, other_rules):
    """Classical yaml: payload holds ONLY non-domain rules (KEYWORD / IP / etc.).

    This matches BM7's convention: the DOMAIN / DOMAIN-SUFFIX entries live
    in the _Domain file (converted to MRS), while the classical file carries
    the remainder. The header still reports FULL-set counts (BM7 does the
    same: its AdvertisingLite.yaml header says TOTAL 38066 with a 375-line
    payload).
    """
    counts = {}
    for t, _ in domain_rules + other_rules:
        counts[t] = counts.get(t, 0) + 1
    total = len(domain_rules) + len(other_rules)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# NAME: {name}",
        "# AUTHOR: Sileec/ClashForD (self-aggregated)",
        f"# UPDATED: {now}",
        f"# SOURCES: {', '.join(sources)}",
    ]
    for t in sorted(counts):
        lines.append(f"# {t}: {counts[t]}")
    lines.append(f"# TOTAL: {total}")
    lines.append("payload:")
    for t, v in other_rules:
        lines.append(f"  - {t},{v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return total


def write_domain(path: Path, name: str, sources, domain_rules):
    counts = {}
    for t, _ in domain_rules:
        counts[t] = counts.get(t, 0) + 1
    total = len(domain_rules)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# NAME: {name}",
        "# AUTHOR: Sileec/ClashForD (self-aggregated)",
        f"# UPDATED: {now}",
        f"# SOURCES: {', '.join(sources)}",
        "# BEHAVIOR: domain",
    ]
    for t in sorted(counts):
        lines.append(f"# {t}: {counts[t]}")
    lines.append(f"# TOTAL: {total}")
    lines.append("payload:")
    for t, v in domain_rules:
        if t == "DOMAIN":
            lines.append(f"  - '{v}'")
        else:
            lines.append(f"  - '.{v}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return total


def build(name: str, inputs, outdir: Path, alibaba: bool):
    """inputs: list of (path, parser). Returns stats dict."""
    rules = []
    sources = []
    for path, parser in inputs:
        parsed = parser(path)
        print(f"  {path.name}: {len(parsed)} rules")
        rules.extend(parsed)
        sources.append(path.name)
    print(f"  raw total: {len(rules)}")
    domain_rules, other_rules = dedup_subsumption(rules)
    print(f"  after dedup+subsumption: {len(domain_rules)} domain, {len(other_rules)} other")
    if alibaba:
        before = len(domain_rules) + len(other_rules)
        domain_rules, other_rules = apply_alibaba_filter(domain_rules, other_rules)
        print(f"  after alibaba filter: removed {before - len(domain_rules) - len(other_rules)}")
    outdir.mkdir(parents=True, exist_ok=True)
    classical_total = write_classical(
        outdir / f"{name}.yaml", name, sources, domain_rules, other_rules
    )
    domain_total = write_domain(
        outdir / f"{name}_Domain.yaml", name, sources, domain_rules
    )
    print(f"  wrote {name}.yaml ({classical_total}) + {name}_Domain.yaml ({domain_total})")
    return {
        "name": name,
        "raw": len(rules),
        "classical": classical_total,
        "domain": domain_total,
        "domain_rules": domain_rules,
        "other_rules": other_rules,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path(".tmp/ads"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--with-anti-ad", action="store_true",
                    help="include anti-AD in AdvertisingLite")
    ap.add_argument("--with-nobyda", action="store_true",
                    help="include NobyDa ND-AD in AdvertisingLite (frozen since 2021-02-27,"
                         " but source of ~99%% of BM7 AdLite entries the fresh sources miss)")
    args = ap.parse_args()

    src = args.src
    print("== Privacy ==")
    build("Privacy", [
        (src / "BanEasyPrivacy.list", parse_typed_file),
        (src / "reject-drop.conf", parse_typed_file),
        (src / "reject-no-drop.conf", parse_typed_file),
    ], args.out, alibaba=False)

    print("== AdvertisingLite ==")
    ad_inputs = [
        (src / "BanAD.list", parse_typed_file),
        (src / "BanEasyList.list", parse_typed_file),
        (src / "BanEasyListChina.list", parse_typed_file),
    ]
    if args.with_anti_ad:
        ad_inputs.append((src / "anti-ad-domains.txt", parse_plain_domains))
    if args.with_nobyda:
        ad_inputs.append((src / "NobyDa-AD_Block.txt", parse_plain_domains))
    build("AdvertisingLite", ad_inputs, args.out, alibaba=True)


if __name__ == "__main__":
    main()
