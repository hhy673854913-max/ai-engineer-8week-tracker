# Tasks

- [x] Task 1: 新增可信源列表数据文件 `data/trusted_sources.json`
  - [x] SubTask 1.1: 定义可信源条目 schema（source 名称、rss URL、tier/可信度等级、是否启用）
  - [x] SubTask 1.2: 初始化一批 AI 相关可信源（官方公告、权威媒体、垂直媒体等）
  - [x] SubTask 1.3: 增加加载与校验函数：缺失/非法时报错并提示修复方式

- [x] Task 2: 在 `models.py` 增加可信源与报表扩展模型
  - [x] SubTask 2.1: 新增 `TrustedSource` 模型
  - [x] SubTask 2.2: 扩展 `PipelineReport` 增加过滤统计字段（after_time_filter/after_ai_filter 等）

- [x] Task 3: 改造 `sources.py` 支持“自动采集前一日 AI 资讯”
  - [x] SubTask 3.1: 实现 `load_trusted_sources()` 并在采集前调用
  - [x] SubTask 3.2: 实现 `fetch_all_trusted_sources(limit)` 聚合多个 RSS 抓取
  - [x] SubTask 3.3: 实现 `filter_previous_day(items, now)` 按前一日时间窗口过滤
  - [x] SubTask 3.4: 实现 `filter_ai_related(items)` 规则/关键词过滤，输出被过滤统计

- [x] Task 4: 更新 `pipeline.py` 接入自动采集与统计
  - [x] SubTask 4.1: 默认自动模式使用可信源列表采集；`--rss` 作为手动覆盖
  - [x] SubTask 4.2: 将过滤统计写入 `PipelineReport` 并落盘到 `report_*.json`
  - [x] SubTask 4.3: 记录本次使用的可信源列表快照到输出目录，保证可回放

- [x] Task 5: 增加最小验证（离线可跑）
  - [x] SubTask 5.1: 用 mock/样本 RSS 条目验证前一日过滤逻辑正确
  - [x] SubTask 5.2: 验证 AI 相关过滤与统计字段写入 report

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 2
- Task 4 depends on Task 3
- Task 5 depends on Task 4
