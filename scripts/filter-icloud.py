#!/usr/bin/env python3
"""
Filter iCloud rules from Apple.yaml / Apple_Domain.yaml
and prepare iCloud domain rules for MRS conversion.

Usage:
    python filter-icloud.py \
        Rules/iCloud.yaml \
        Rules/Apple.yaml \
        Rules/Apple.yaml \
        .tmp/rules/Apple_Domain.yaml \
        .tmp/rules/Apple_Domain_Filtered.yaml \
        .tmp/rules/iCloud_Domain.txt

Processing:
    1. Read iCloud.yaml
    2. Detect iCloud DOMAIN / DOMAIN-SUFFIX / DOMAIN-KEYWORD rules
    3. Remove matching iCloud rules from Apple.yaml
    4. Remove matching iCloud domains from Apple_Domain.yaml
    5. Generate MRS-compatible iCloud_Domain.txt

MRS domain text format:
    DOMAIN        -> example.com
    DOMAIN-SUFFIX -> +.example.com

DOMAIN-KEYWORD is intentionally excluded from MRS because
Mihomo domain MRS cannot preserve Clash DOMAIN-KEYWORD semantics.
"""

import argparse
import re
from pathlib import Path


# ============================================================
# Domain normalization
# ============================================================

def normalize_domain(domain: str) -> str:
    """
    Normalize a domain for comparison.

    Examples:
        icloud.com
        .icloud.com
        +.icloud.com
        'icloud.com'
        "icloud.com."
    """

    domain = domain.strip().strip("'\"").lower()

    if domain.startswith("+."):
        domain = domain[2:]
    elif domain.startswith("."):
        domain = domain[1:]

    return domain.rstrip(".")


# ============================================================
# Parse Clash rule
# ============================================================

def parse_clash_rule(line: str):
    """
    Parse a Clash classical rule.

    Supports:
        - DOMAIN,example.com
        - DOMAIN-SUFFIX,example.com
        - DOMAIN-KEYWORD,icloud
        - DOMAIN-SUFFIX,example.com,Apple

    Returns:
        (rule_type, value)

    Example:
        "- DOMAIN-SUFFIX,icloud.com,Apple"
        -> ("DOMAIN-SUFFIX", "icloud.com")
    """

    stripped = line.strip()

    if not stripped.startswith("-"):
        return None, None

    stripped = stripped[1:].strip()

    if "," not in stripped:
        return None, None

    parts = stripped.split(",")

    if len(parts) < 2:
        return None, None

    rule_type = parts[0].strip().upper()
    value = parts[1].strip().strip("'\"")

    return rule_type, value


# ============================================================
# Parse iCloud source rules
# ============================================================

def parse_icloud_rules(path: Path):
    """
    Read iCloud.yaml and return:

        exact domains
        suffix domains
        keywords

    DOMAIN is kept separately because exact-domain rules are
    different from DOMAIN-SUFFIX rules.

    Returns:
        exact_domains, suffixes, keywords
    """

    exact_domains = set()
    suffixes = set()
    keywords = set()

    for raw_line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        rule_type, value = parse_clash_rule(raw_line)

        if not rule_type or not value:
            continue

        if rule_type == "DOMAIN":
            exact_domains.add(
                normalize_domain(value)
            )

        elif rule_type == "DOMAIN-SUFFIX":
            suffixes.add(
                normalize_domain(value)
            )

        elif rule_type == "DOMAIN-KEYWORD":
            keywords.add(
                normalize_domain(value)
            )

    return exact_domains, suffixes, keywords


# ============================================================
# Parse iCloud domain rules for MRS
# ============================================================

def parse_icloud_domain_rules(path: Path):
    """
    Extract DOMAIN and DOMAIN-SUFFIX rules from Clash
    classical YAML and convert them to Mihomo domain text.

    Output:

        DOMAIN
            example.com

        DOMAIN-SUFFIX
            +.example.com

    DOMAIN-KEYWORD is intentionally excluded.
    """

    rules = []

    for raw_line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        rule_type, value = parse_clash_rule(raw_line)

        if not rule_type or not value:
            continue

        domain = normalize_domain(value)

        if not domain:
            continue

        if rule_type == "DOMAIN":
            rules.append(domain)

        elif rule_type == "DOMAIN-SUFFIX":
            rules.append(
                f"+.{domain}"
            )

    return sorted(set(rules))


# ============================================================
# Domain matching
# ============================================================

def domain_matches_suffix(
    domain: str,
    suffix: str,
) -> bool:
    """
    Check whether a domain belongs to a DOMAIN-SUFFIX rule.

    Example:

        domain:
            gateway.icloud.com

        suffix:
            icloud.com

        -> True
    """

    domain = normalize_domain(domain)
    suffix = normalize_domain(suffix)

    if not domain or not suffix:
        return False

    return (
        domain == suffix
        or domain.endswith("." + suffix)
    )


def domain_is_icloud(
    domain: str,
    exact_domains,
    suffixes,
    keywords,
) -> bool:
    """
    Determine whether a domain belongs to iCloud rules.
    """

    domain = normalize_domain(domain)

    if not domain:
        return False

    # --------------------------------------------------------
    # Exact DOMAIN
    # --------------------------------------------------------

    if domain in exact_domains:
        return True

    # --------------------------------------------------------
    # DOMAIN-SUFFIX
    # --------------------------------------------------------

    for suffix in suffixes:
        if domain_matches_suffix(
            domain,
            suffix,
        ):
            return True

    # --------------------------------------------------------
    # DOMAIN-KEYWORD
    # --------------------------------------------------------

    for keyword in keywords:
        if keyword and keyword in domain:
            return True

    return False


# ============================================================
# Check whether a Clash rule is iCloud
# ============================================================

def rule_is_icloud(
    rule: str,
    exact_domains,
    suffixes,
    keywords,
) -> bool:
    """
    Determine whether a Clash classical rule should be
    removed because it belongs to iCloud.

    Supported:
        DOMAIN
        DOMAIN-SUFFIX
        DOMAIN-KEYWORD

    Other rule types are left untouched.
    """

    rule_type, value = parse_clash_rule(rule)

    if not rule_type or not value:
        return False

    # --------------------------------------------------------
    # DOMAIN / DOMAIN-SUFFIX
    # --------------------------------------------------------

    if rule_type in {
        "DOMAIN",
        "DOMAIN-SUFFIX",
    }:
        return domain_is_icloud(
            value,
            exact_domains,
            suffixes,
            keywords,
        )

    # --------------------------------------------------------
    # DOMAIN-KEYWORD
    # --------------------------------------------------------

    if rule_type == "DOMAIN-KEYWORD":
        keyword = normalize_domain(value)

        if not keyword:
            return False

        # Exact keyword match
        if keyword in keywords:
            return True

        # One iCloud keyword contains the other
        for icloud_keyword in keywords:
            if (
                icloud_keyword
                and (
                    icloud_keyword in keyword
                    or keyword in icloud_keyword
                )
            ):
                return True

        # A keyword matching an iCloud suffix
        for suffix in suffixes:
            if keyword == suffix:
                return True

        return False

    return False


# ============================================================
# Filter Apple.yaml
# ============================================================

def filter_clash_yaml(
    input_path: Path,
    output_path: Path,
    exact_domains,
    suffixes,
    keywords,
):
    """
    Remove iCloud-related rules from a Clash classical YAML.

    This is primarily used for:

        Rules/Apple.yaml

    The original file structure and non-iCloud rules are kept.
    """

    lines = input_path.read_text(
        encoding="utf-8"
    ).splitlines()

    output_lines = []
    removed = 0

    for line in lines:

        if line.lstrip().startswith("- "):

            if rule_is_icloud(
                line,
                exact_domains,
                suffixes,
                keywords,
            ):
                removed += 1
                continue

        output_lines.append(line)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        "\n".join(output_lines) + "\n",
        encoding="utf-8",
    )

    return removed


# ============================================================
# Filter Apple_Domain.yaml
# ============================================================

def filter_domain_yaml(
    input_path: Path,
    output_path: Path,
    exact_domains,
    suffixes,
    keywords,
):
    """
    Remove iCloud-related domains from Apple_Domain.yaml.

    Apple_Domain.yaml may be either:

        DOMAIN-SUFFIX,icloud.com

    or:

        +.icloud.com

    or:

        icloud.com

    This function supports all three forms.
    """

    lines = input_path.read_text(
        encoding="utf-8"
    ).splitlines()

    output_lines = []
    removed = 0

    for line in lines:

        stripped = line.strip()

        if not stripped.startswith("- "):
            output_lines.append(line)
            continue

        value = stripped[2:].strip()

        # ----------------------------------------------------
        # Case 1:
        # Clash-style DOMAIN / DOMAIN-SUFFIX rule
        # ----------------------------------------------------

        rule_type, rule_value = parse_clash_rule(
            stripped
        )

        if rule_type in {
            "DOMAIN",
            "DOMAIN-SUFFIX",
            "DOMAIN-KEYWORD",
        }:

            if rule_is_icloud(
                stripped,
                exact_domains,
                suffixes,
                keywords,
            ):
                removed += 1
                continue

            output_lines.append(line)
            continue

        # ----------------------------------------------------
        # Case 2:
        # Plain domain / MRS-style source
        #
        # Examples:
        #     icloud.com
        #     .icloud.com
        #     +.icloud.com
        # ----------------------------------------------------

        domain = normalize_domain(value)

        if domain_is_icloud(
            domain,
            exact_domains,
            suffixes,
            keywords,
        ):
            removed += 1
            continue

        output_lines.append(line)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        "\n".join(output_lines) + "\n",
        encoding="utf-8",
    )

    return removed


# ============================================================
# Generate iCloud MRS domain source
# ============================================================

def write_mrs_domain_source(
    input_path: Path,
    output_path: Path,
):
    """
    Convert iCloud DOMAIN / DOMAIN-SUFFIX rules into
    Mihomo domain-rule text format.
    """

    rules = parse_icloud_domain_rules(
        input_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        "\n".join(rules) + "\n",
        encoding="utf-8",
    )

    return rules


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Filter iCloud rules from Apple rule sources "
            "and prepare MRS-compatible domain rules."
        )
    )

    parser.add_argument(
        "icloud",
        help="Source iCloud.yaml",
    )

    parser.add_argument(
        "apple",
        help="Apple.yaml input",
    )

    parser.add_argument(
        "apple_filtered",
        help="Apple.yaml output",
    )

    parser.add_argument(
        "apple_domain",
        help="Apple_Domain.yaml input",
    )

    parser.add_argument(
        "apple_domain_filtered",
        help="Apple_Domain.yaml output",
    )

    parser.add_argument(
        "icloud_domain_output",
        help="MRS-compatible iCloud domain text output",
    )

    args = parser.parse_args()

    icloud_path = Path(
        args.icloud
    )

    apple_path = Path(
        args.apple
    )

    apple_filtered_path = Path(
        args.apple_filtered
    )

    apple_domain_path = Path(
        args.apple_domain
    )

    apple_domain_filtered_path = Path(
        args.apple_domain_filtered
    )

    icloud_domain_output_path = Path(
        args.icloud_domain_output
    )

    # ========================================================
    # Parse iCloud rules
    # ========================================================

    (
        exact_domains,
        suffixes,
        keywords,
    ) = parse_icloud_rules(
        icloud_path
    )

    if not (
        exact_domains
        or suffixes
        or keywords
    ):
        raise RuntimeError(
            f"No iCloud DOMAIN, DOMAIN-SUFFIX "
            f"or DOMAIN-KEYWORD rules found in "
            f"{icloud_path}"
        )

    # ========================================================
    # Filter Apple.yaml
    # ========================================================

    removed_apple = filter_clash_yaml(
        apple_path,
        apple_filtered_path,
        exact_domains,
        suffixes,
        keywords,
    )

    # ========================================================
    # Filter Apple_Domain.yaml
    # ========================================================

    removed_apple_domain = filter_domain_yaml(
        apple_domain_path,
        apple_domain_filtered_path,
        exact_domains,
        suffixes,
        keywords,
    )

    # ========================================================
    # Generate iCloud MRS domain source
    # ========================================================

    mrs_rules = write_mrs_domain_source(
        icloud_path,
        icloud_domain_output_path,
    )

    # ========================================================
    # Output summary
    # ========================================================

    print(
        "iCloud rules loaded:"
    )

    print(
        f"  DOMAIN: {len(exact_domains)}"
    )

    print(
        f"  DOMAIN-SUFFIX: {len(suffixes)}"
    )

    print(
        f"  DOMAIN-KEYWORD: {len(keywords)}"
    )

    print(
        f"iCloud MRS domain rules: "
        f"{len(mrs_rules)}"
    )

    print(
        f"Removed from Apple.yaml: "
        f"{removed_apple}"
    )

    print(
        f"Removed from Apple_Domain.yaml: "
        f"{removed_apple_domain}"
    )

    print(
        "iCloud filtering completed successfully."
    )


if __name__ == "__main__":
    main()