# Whisper 自托管方案：为什么这么定

> 本文件记录 Sileec/ClashForD 自托管 Whisper 方案背后的决策理由。配置本身在 `config/whisper-scheme-selfhost.yaml`；本文件回答"为什么"，不重复"是什么"。
>
> 2026-11-19 初版。本地副本与仓库副本（`docs/whisper-rationale.md`）互为备份，改动时两边同步。

## 背景

- 方案源头是 kiki 的 Whisper.js（2026-11-03 起自托管：脚本存自己仓库，规则源指向自建管线）。
- 2026-11-05 kiki 把全部规则源从 blackmatrix7（BM7）切到 MagicRule；咱们评估后没跟。
- BM7 老仓库 2026-12-31 彻底停更。

## 为什么冻结 ChinaMax（2026-11-13，方案 C）

- 中国域名变化慢，冻结一个验过的版本最稳。
- 冻结时已验过 browserleaks.com 不在里面。
- BM7 停更后想跟活的也跟不上，冻结是被动也是主动选择。
- 快变的部分（广告/隐私）不靠冻结，走自聚合。

## 为什么服务类换上游到 meta-rules-dat

- BM7 死了，Google、Apple、Telegram 等服务类规则需要一个还在维护的源。
- meta-rules-dat 是 mihomo 官方在维护的，MRS 二进制格式加载快、省内存。
- 但它有坑：GeoSite CN 收了泄漏检测域名（browserleaks.com、whatismyip.akamai.com 等），2025 年 7 月已报上游，截至 2026-11-18 未修。所以只用它服务类，中国域名不用 GEOSITE,CN，继续走冻结的 ChinaMax + GEOIP,CN。

## 为什么加 Config Doctor

- 配置是多源拼起来的：自聚合 + 冻结 + MRS + 内联 + 覆写脚本。错了不会报错，只会静默走错路（例：anthropic.auth0.com 被前面的 `+.auth0.com` 截胡）。
- Doctor 让每次重建跑 9 项检查，坏了拦下来，不悄悄发一个坏配置。
- 已救过一次：2026-11-18 fake-ip-filter 切 rule 模式，先推 Doctor 第 4 项修复，否则当晚重建必失败。

## 决策原则

- 慢变的冻结、快变的自聚合、服务类跟维护中的上游、小修补内联（几百条以下内联更省，10 条约 1–2KB）。
- 上游变了先评估：有没有过宽条目、会不会冲掉已钉的规则、Doctor 过不过。不盲跟。
- kiki 的更新只摘域名/规则，不跟他的 MagicRule 远程集（核过有过宽条目：Anthropic 集含 storage.googleapis.com、intercom.io、sentry.io 及 datadog/sentry 关键词规则；Gemini 集含 apis.google.com；Google 集含 DOMAIN-KEYWORD,google）。

## 关键 commit 索引

- `8d5401d`（2026-11-17）：从 kiki 新集摘 10 条域名内联，规则 223→233
- `e5218de`（2026-11-18）：3 条泄漏域名显式规则钉 PROXY-Gate，规则 233→236
- `3508729`（2026-11-18）：DNS fake-ip-filter 切 rule 模式
- `8b84c09`（2026-11-18）：Config Doctor 第 4 项认 rule 模式
- `6741920`（2026-11-16）：PCC 显式规则 3 行
- `ff7651e`（2026-11-07）：hatch.metaaivm.com 放行（抄 kiki 的修复作保险）
- `ea12cdd`（2026-11-11）：statsig.anthropic.com 白名单

## 后续方向

- 12 月：BM7 彻底停更前，准备好自聚合迁移（2026-11-05 已定，12 月初复议）。
- 盯 kiki 上游：只摘域名，不跟 MagicRule 远程集。
- 盯 meta-rules-dat：GeoSite CN 泄漏域名修了没有，修了可重新评估。
- Doctor：每出一个新故障模式就加一项检查。
- 用户态度：DNS 泄漏"不测就不漏，漏了就漏了"——DNS 层改动只影响测试显示；includeAllNetworks 保持开着，图断网保护。
