#!/usr/bin/env python3

import argparse
import re
from pathlib import Path


DOMAIN_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
}

IP_TYPES = {
    "IP-CIDR",
    "IP-CIDR6",
}


def normalize_domain(domain: str) -> str:
    domain = domain.strip().strip("'\"").lower()

    if domain.startswith("+."):
        domain = domain[2:]
    elif domain.startswith("."):
        domain = domain[1:]

    return domain.rstrip(".")


def parse_rule(line: str):
    match = re.match(
        r"^-\s*([A-Z0-9-]+)\s*,\s*(.+?)\s*$",
        line.strip(),
        re.IGNORECASE,
    )

    if not match:
        return None, None

    return (
        match.group(1).upper(),
        match.group(2).strip().strip("'\""),
    )


def convert_rules(
    input_path: Path,
    domain_output: Path,
    ip_output: Path,
):
    domain_rules = []
    ip_rules = []

    for raw_line in input_path.read_text(
        encoding="utf-8"
    ).splitlines():

        rule_type, value = parse_rule(raw_line)

        if not rule_type or not value:
            continue

        if rule_type in DOMAIN_TYPES:
            domain = normalize_domain(value)

            if rule_type == "DOMAIN":
                domain_rules.append(domain)

            elif rule_type == "DOMAIN-SUFFIX":
                domain_rules.append(f"+.{domain}")

        elif rule_type in IP_TYPES:
            ip_rules.append(value)

    domain_rules = sorted(set(domain_rules))
    ip_rules = sorted(set(ip_rules))

    domain_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ip_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    domain_output.write_text(
        "\n".join(domain_rules) + "\n",
        encoding="utf-8",
    )

    ip_output.write_text(
        "\n".join(ip_rules) + "\n",
        encoding="utf-8",
    )

    return domain_rules, ip_rules


def main():
    parser = argparse.ArgumentParser(
        description="Prepare Copilot domain/IP rules for Mihomo MRS."
    )

    parser.add_argument(
        "input",
        type=Path,
    )

    parser.add_argument(
        "domain_output",
        type=Path,
    )

    parser.add_argument(
        "ip_output",
        type=Path,
    )

    args = parser.parse_args()

    domain_rules, ip_rules = convert_rules(
        args.input,
        args.domain_output,
        args.ip_output,
    )

    print(
        f"Copilot domain rules: {len(domain_rules)}"
    )

    print(
        f"Copilot IP-CIDR rules: {len(ip_rules)}"
    )


if __name__ == "__main__":
    main()