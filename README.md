# Hako 配置仓库

Hako Clash（Mac）的全部配置收归自有仓库：规则自动生产、策略静态维护、地区分组动态注入。

## 结构

```
.
├── .github/workflows/update-rules.yml  # 每天 06:00 UTC 重建 rules/（有变化才提交）
├── config/
│   ├── whisper-scheme.yaml             # 规则方案：静态策略（Hako 规则库引用）
│   └── whisper-scheme-selfhost.yaml    # 自托管版：规则集合指向本仓库 rules/
├── js/
│   ├── whisper.js                      # 旧全量覆写脚本（退役保留）
│   └── whisper-regions.js              # 覆写脚本：只做地区分组（Hako Profile 引用）
├── rules/                              # 产物：26 个规则文件，全部由 Actions 生成，人不手改
└── scripts/
    ├── filter-*.py                     # 13 个 filter 脚本（kiki 开源，原样引入）
    └── sync-threads.py                 # Threads 专版（blackmatrix7 + 本地补充域名）
```

分工铁律：**不依赖节点名的进 `config/`，按节点名正则分组的进 `js/`，`rules/` 永远是产物。**

## 首次使用

1. 上传全部文件到 GitHub 公开仓库。
2. `config/whisper-scheme-selfhost.yaml` 里的仓库地址已填好（Sileec/ClashForD）。
3. Actions 页手动触发一次 `Update Rules`，确认 `rules/` 被填满（26 个文件）。
4. Hako：规则库添加 `config/whisper-scheme-selfhost.yaml` 的 raw 链接；
   Profile 里规则方案选它，覆写脚本选 `js/whisper-regions.js` 的 raw 链接（旧 whisper.js 停用）。

## Threads

`scripts/sync-threads.py` 从 blackmatrix7 抓 Threads 规则并合并本地补充
（`threads.com` / `threads.net` / `threadsusercontent.com`——上游目前只有 1 条），
输出 `rules/Threads_Domain.mrs`，方案里走独立的 `Threads` 策略组。

## 阶段

- 阶段一（现在）：kiki 同层级——吃 blackmatrix7 成品，自己转制。
- 阶段二（未来）：black7 同层级——从原始多源自己聚合。
