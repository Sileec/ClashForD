#!/usr/bin/env python3
"""ClashForD 配置体检（Config Doctor）。

设计来源：Kianuni/AppleFlow 的 Config Doctor（auditor.js）——只拿模式，不照搬
检查项：Siri 直连 / fake-ip-filter（Siri）那几项对本仓库不适用（不用普通话 Siri），
这里只保留与本仓库相关的检查。

用法（仓库根目录）：
    python3 scripts/config_doctor.py [--config PATH] [--rules DIR] [--mihomo PATH]

    --config  待体检的 Mihomo 配置（默认 config/whisper-scheme-selfhost.yaml）
    --rules   规则目录（默认 rules/，仅 MRS 漂移检查用）
    --mihomo  mihomo 可执行文件路径；不传则跳过 MRS 漂移检查

退出码：任一检查 FAIL 则退出 1；只有 WARN/PASS 则退出 0。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# PCC 关键域名：必须有显式规则指向代理组，且排在 Apple 兜底规则之前。
# ss-cleanup-proxy-prod.us-east-1m.app.apple.com 在 app.apple.com 子域内，不单列。
PCC_DOMAINS = [
    "issuer.apple.com",
    "ropes.apple.com",
    "app.apple.com",
    "gspe1-ssl.ls.apple.com",
    "mask.icloud.com",
    "mask-h2.icloud.com",
    "mask-api.icloud.com",
    "apple-relay.apple.com",
    "apple-relay.cloudflare.com",
    "apple-relay.fastly-edge.com",
    "apple-relay.akamaized.net",
    "cp4.cloudflare.com",
]

# MRS 漂移检查只查 geosite 本应覆盖的子集：apple-relay 的 CDN 变体与 cp4
# 从来只靠 yaml 显式规则（geosite 里没有），放进漂移检查只会产生永久噪音。
MRS_EXPECTED_DOMAINS = [
    "issuer.apple.com",
    "ropes.apple.com",
    "app.apple.com",
    "gspe1-ssl.ls.apple.com",
    "mask.icloud.com",
    "mask-h2.icloud.com",
    "mask-api.icloud.com",
]
CATCHALL_RULESETS = ("iCloud", "Apple", "Apple_Domain")

# APNs 网段（AppleFlow 清单，与 yaml 307-318 行一致）。
APNS_V4 = [
    "17.249.0.0/16",
    "17.252.0.0/16",
    "17.57.144.0/22",
    "17.188.128.0/18",
    "17.188.20.0/23",
]
APNS_V6 = [
    "2403:300:a42::/48",
    "2403:300:a51::/48",
    "2620:149:a44::/48",
    "2a01:b740:a42::/48",
]

FAKE_IP_REQUIRED = ["*.push.apple.com", "+.push.apple.com"]


class Check:
    def __init__(self, name: str):
        self.name = name
        self.status = "PASS"
        self.details: list[str] = []

    def fail(self, msg: str):
        self.status = "FAIL"
        self.details.append(msg)

    def warn(self, msg: str):
        if self.status == "PASS":
            self.status = "WARN"
        self.details.append(msg)

    def ok(self, msg: str):
        self.details.append(msg)


def domain_covered(domain: str, rtype: str, value: str) -> bool:
    """规则 (rtype, value) 是否覆盖域名 domain。"""
    if rtype == "DOMAIN":
        return value == domain
    if rtype == "DOMAIN-SUFFIX":
        return domain == value or domain.endswith("." + value)
    return False


def parse_rule(line: str):
    """解析一条规则行，返回 (type, value, policy, raw)；解析不了返回 None。"""
    text = line.strip()
    if not text.startswith("- "):
        return None
    body = text[2:].strip()
    if not body or body.startswith("#"):
        return None
    parts = [p.strip() for p in body.split(",")]
    rtype = parts[0]
    if rtype in ("MATCH", "FINAL"):
        return (rtype, "", parts[1] if len(parts) > 1 else "", text)
    if len(parts) < 3:
        return None
    return (rtype, parts[1], parts[2], text)


def load_config(path: Path):
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    lines = text.splitlines()
    # 按顺序把 rules 列表的每条规则映射到原始行号（1-based）。
    rule_lines: list[tuple[int, str]] = []
    in_rules = False
    for i, line in enumerate(lines, start=1):
        if line.startswith("rules:"):
            in_rules = True
            continue
        if in_rules:
            if line and not line.startswith((" ", "\t", "#")) and not line.startswith("- "):
                break
            if line.strip().startswith("- ") and not line.strip().startswith("- #"):
                rule_lines.append((i, line))
    rules = []
    for lineno, line in rule_lines:
        parsed = parse_rule(line)
        if parsed:
            rules.append((lineno, *parsed))
    return data, rules


def check_pcc_explicit(rules, check: Check):
    missing = []
    for domain in PCC_DOMAINS:
        covered = False
        for lineno, rtype, value, policy, raw in rules:
            if domain_covered(domain, rtype, value):
                if policy in ("DIRECT", "REJECT"):
                    check.fail(f"{domain} 被显式规则指向 {policy}（{lineno} 行），应走代理组")
                covered = True
                break
        if not covered:
            missing.append(domain)
    if missing:
        check.fail("以下 PCC 域名无显式规则（仅靠 geosite 覆盖，geosite 一掉就静默失效）：" + ", ".join(missing))
    else:
        check.ok(f"{len(PCC_DOMAINS)} 个 PCC 域名均有显式代理规则")


def check_pcc_order(rules, check: Check):
    catchall_line = None
    for lineno, rtype, value, policy, raw in rules:
        if rtype == "RULE-SET" and value in CATCHALL_RULESETS:
            catchall_line = lineno
            break
    if catchall_line is None:
        check.fail("未找到 Apple/iCloud 兜底 RULE-SET 行")
        return
    shadowed = []
    for lineno, rtype, value, policy, raw in rules:
        for domain in PCC_DOMAINS:
            if domain_covered(domain, rtype, value) and lineno > catchall_line:
                shadowed.append(f"{domain}（{lineno} 行，兜底在 {catchall_line} 行）")
                break
    if shadowed:
        check.fail("以下 PCC 规则排在兜底规则之后，会被截胡：" + "; ".join(shadowed))
    else:
        check.ok(f"全部 PCC 显式规则都在兜底行（{catchall_line} 行）之前")


def check_no_quic_block(rules, check: Check):
    bad = []
    for lineno, rtype, value, policy, raw in rules:
        low = raw.lower()
        if policy != "REJECT":
            continue
        if ",udp" in low or "dst-port,443" in low or "network,udp" in low:
            bad.append(f"{lineno} 行: {raw.strip()}")
    if bad:
        check.fail("发现 UDP 443 / QUIC 拦截规则（会阻断 PCC OHTTP 握手）：" + "; ".join(bad))
    else:
        check.ok("无 UDP 443 / QUIC 拦截规则")


def check_fake_ip_filter(data, check: Check):
    filt = (data.get("dns") or {}).get("fake-ip-filter") or []
    if any(item in filt for item in FAKE_IP_REQUIRED):
        check.ok("fake-ip-filter 含 push.apple.com")
    else:
        check.fail("fake-ip-filter 缺少 *.push.apple.com（APNs 推送可能被 Fake-IP 误伤）")


def check_apns_complete(rules, check: Check):
    have_v4 = {v for _, t, v, _, _ in rules if t == "IP-CIDR"}
    have_v6 = {v for _, t, v, _, _ in rules if t == "IP-CIDR6"}
    missing = [c for c in APNS_V4 if c not in have_v4] + [c for c in APNS_V6 if c not in have_v6]
    if missing:
        check.fail("APNs 网段缺失：" + ", ".join(missing))
    else:
        check.ok("APNs 5 段 IPv4 + 4 段 IPv6 齐全")


def check_no_overbroad_akadns(rules, check: Check):
    bad = []
    for lineno, rtype, value, policy, raw in rules:
        if rtype in ("DOMAIN-SUFFIX", "DOMAIN-KEYWORD") and value == "akadns.net":
            bad.append(f"{lineno} 行: {raw.strip()}")
    if bad:
        check.fail("发现未加限定的 akadns.net 规则（会误伤第三方网站）：" + "; ".join(bad))
    else:
        check.ok("无未加限定的 akadns.net 规则（icloud.com.akadns.net 限定版不受影响）")


def check_ruleset_refs(data, rules, check: Check):
    providers = set((data.get("rule-providers") or {}).keys())
    missing = sorted({v for _, t, v, _, _ in rules if t == "RULE-SET" and v not in providers})
    if missing:
        check.fail("以下 RULE-SET 无对应 rule-providers 定义（配置加载会失败）：" + ", ".join(missing))
    else:
        check.ok(f"全部 RULE-SET 引用均有 provider 定义（{len(providers)} 个）")


def check_policy_refs(data, rules, check: Check):
    groups = {g.get("name") for g in (data.get("proxy-groups") or []) if g.get("name")}
    allowed = groups | {"DIRECT", "REJECT"}
    bad = sorted({p for _, _, _, p, _ in rules if p and p not in allowed})
    if bad:
        check.fail("以下规则指向不存在的策略组（配置加载会失败）：" + ", ".join(bad))
    else:
        check.ok(f"全部规则的策略组均存在（{len(groups)} 个组）")


def check_mrs_pcc_drift(rules_dir: Path, mihomo: Path, check: Check):
    mrs = rules_dir / "Apple_Domain.mrs"
    if not mrs.exists():
        check.warn(f"未找到 {mrs}，跳过 MRS 漂移检查")
        return
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "apple_domain.txt"
        r = subprocess.run(
            [str(mihomo), "convert-ruleset", "domain", "mrs", str(mrs), str(out)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0 or not out.exists():
            check.fail(f"Apple_Domain.mrs 解码失败（文件可能损坏）：{r.stderr.strip()[:200]}")
            return
        entries = [ln.strip() for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # MRS 文本条目形如 +.example.com 或 example.com，转成 (type, value) 再判覆盖。
    parsed = []
    for e in entries:
        if e.startswith("+."):
            parsed.append(("DOMAIN-SUFFIX", e[2:]))
        elif e.startswith("."):
            parsed.append(("DOMAIN-SUFFIX", e[1:]))
        else:
            parsed.append(("DOMAIN", e))
    missing = []
    for domain in MRS_EXPECTED_DOMAINS:
        if not any(domain_covered(domain, t, v) for t, v in parsed):
            missing.append(domain)
    if missing:
        check.warn("geosite Apple_Domain 已不再覆盖以下 PCC 域名（yaml 显式规则仍在兜底，路由不受影响）：" + ", ".join(missing))
    else:
        check.ok(f"geosite Apple_Domain 仍覆盖应覆盖的 {len(MRS_EXPECTED_DOMAINS)} 个 PCC 域名（{len(entries)} 条）")


def main() -> int:
    parser = argparse.ArgumentParser(description="ClashForD 配置体检")
    parser.add_argument("--config", default="config/whisper-scheme-selfhost.yaml")
    parser.add_argument("--rules", default="rules")
    parser.add_argument("--mihomo", default=None)
    args = parser.parse_args()

    config_path = Path(args.config)
    data, rules = load_config(config_path)
    print(f"config: {config_path}（{len(rules)} 条规则）")

    checks: list[Check] = []
    c1 = Check("1 PCC 显式规则")
    check_pcc_explicit(rules, c1)
    checks.append(c1)
    c2 = Check("2 PCC 规则排序（防兜底截胡）")
    check_pcc_order(rules, c2)
    checks.append(c2)
    c3 = Check("3 无 QUIC 拦截")
    check_no_quic_block(rules, c3)
    checks.append(c3)
    c4 = Check("4 fake-ip-filter（APNs）")
    check_fake_ip_filter(data, c4)
    checks.append(c4)
    c5 = Check("5 APNs 网段齐全")
    check_apns_complete(rules, c5)
    checks.append(c5)
    c6 = Check("6 无过宽 akadns 规则")
    check_no_overbroad_akadns(rules, c6)
    checks.append(c6)
    c7 = Check("7 RULE-SET 引用存在")
    check_ruleset_refs(data, rules, c7)
    checks.append(c7)
    c8 = Check("8 策略组引用存在")
    check_policy_refs(data, rules, c8)
    checks.append(c8)
    if args.mihomo:
        c9 = Check("9 geosite Apple_Domain 漂移（WARN）")
        check_mrs_pcc_drift(Path(args.rules), Path(args.mihomo).resolve(), c9)
        checks.append(c9)

    n_fail = n_warn = 0
    for c in checks:
        mark = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[c.status]
        print(f"[{mark}] {c.name}")
        for d in c.details:
            print(f"      {d}")
        n_fail += c.status == "FAIL"
        n_warn += c.status == "WARN"
    print(f"结果：{len(checks) - n_fail - n_warn} 通过，{n_warn} 警告，{n_fail} 失败")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
