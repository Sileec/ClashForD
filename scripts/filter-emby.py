#!/usr/bin/env python3

import argparse
import re
from pathlib import Path


DOMAIN_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
}


def normalize_domain(domain: str) -> str:
    domain = domain.strip().strip("'\"").lower()

    if domain.startswith("+."):
        domain = domain[2:]
    elif domain.startswith("."):
        domain = domain[1:]

    return domain.rstrip(".")


def convert_emby_rules(
    input_path: Path,
    output_path: Path,
):
    """
    Convert Emby Clash classical rules into
    Mihomo domain-rule text.

    DOMAIN        -> exact domain
    DOMAIN-SUFFIX -> +.domain

    DOMAIN-KEYWORD and PROCESS-NAME are excluded.
    """

    rules = []

    for raw_line in input_path.read_text(
        encoding="utf-8"
    ).splitlines():

        line = raw_line.strip()

        match = re.match(
            r"^-\s*([A-Z0-9-]+)\s*,\s*(.+?)\s*$",
            line,
            re.IGNORECASE,
        )

        if not match:
            continue

        rule_type = match.group(1).upper()
        value = normalize_domain(match.group(2))

        if rule_type not in DOMAIN_TYPES:
            continue

        if not value:
            continue

        if rule_type == "DOMAIN":
            rules.append(value)

        elif rule_type == "DOMAIN-SUFFIX":
            rules.append(f"+.{value}")

    rules = sorted(set(rules))

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        "\n".join(rules) + "\n",
        encoding="utf-8",
    )

    return rules


def main():
    parser = argparse.ArgumentParser(
        description="Prepare Emby domain rules for Mihomo MRS."
    )

    parser.add_argument(
        "input",
        type=Path,
    )

    parser.add_argument(
        "output",
        type=Path,
    )

    args = parser.parse_args()

    rules = convert_emby_rules(
        args.input,
        args.output,
    )

    print(
        f"Emby MRS domain rules: {len(rules)}"
    )


if __name__ == "__main__":
    main()