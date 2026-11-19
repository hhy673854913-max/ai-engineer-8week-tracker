# Checklist

- [x] `data/trusted_sources.json` 存在且包含 AI 相关可信源条目（含 rss/tier/enabled 字段）
- [x] 采集流程在运行时会加载可信源列表，且列表缺失/非法会快速失败并给出清晰提示
- [x] 自动采集模式默认基于可信源列表抓取，不再需要手动传入 `--rss`
- [x] 采集结果仅保留“前一日”发布的资讯，时间窗口逻辑有测试或样例验证
- [x] 采集/处理流程包含 AI 相关性过滤，且被过滤数量会记录到报表
- [x] `PipelineReport` 与 `report_*.json` 包含过滤统计字段（至少含 after_time_filter/after_ai_filter）
- [x] 输出目录会保存本次使用的可信源快照，保证可回放
- [x] `--mock` 离线模式仍可运行，不被本次改动破坏