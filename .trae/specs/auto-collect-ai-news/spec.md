# M1 智能资讯简报：可信源维护 + 自动采集前一日 AI 资讯 Spec

## Why
当前 `sources.py` 的 RSS 源依赖 `--rss` 参数手动传入，没有“可信源列表”概念，也没有“自动全网搜集前一日 AI 相关资讯”的自动化采集能力。用户希望：每次采集前先维护可信源列表，再基于该列表自动采集**前一日**的 AI 相关资讯。

## What Changes
- 新增“可信源列表”数据文件与维护机制：在采集前读取/生成可信源列表（AI 相关可信源）。
- 采集器改为**自动采集模式**：默认基于可信源列表自动抓取，不再要求用户手动传入 RSS 地址；手动 `--rss` 保留作为覆盖/调试用。
- 采集目标限定为**前一日**发布的资讯：对条目按 `published_at` 做时间过滤，仅保留前一日 00:00–24:00 的内容。
- 采集结果仅保留 **AI 相关**条目：在抽取/入库前增加 AI 相关性过滤（规则 + 可选 LLM 判定）。
- 生成产物中记录可信源列表快照与过滤统计，保证可回放与审计。

## Impact
- Affected specs: 数据采集、过滤、报表统计
- Affected code:
  - `code/week02/m1_brief/sources.py`（新增可信源加载、AI 相关过滤、前一日时间过滤、自动 RSS 聚合）
  - `code/week02/m1_brief/pipeline.py`（默认自动采集；新增过滤统计写入 report）
  - `code/week02/m1_brief/models.py`（新增可信源模型/配置模型、report 字段扩展）
  - `data/trusted_sources.json`（新增可信源列表数据文件）
  - `code/week02/m1_brief/extract.py`（可选：AI 相关性预过滤提示/规则）

## ADDED Requirements
### Requirement: Trusted Source List
The system SHALL provide a trusted source list stored as data (e.g., `data/trusted_sources.json`) and expose an API to load/validate it before fetching.

#### Scenario: Load trusted sources before collection
- **WHEN** the pipeline starts in auto mode
- **THEN** it loads trusted sources from the data file and fetches only from these sources

#### Scenario: Trusted source list missing or invalid
- **WHEN** the trusted source file is missing or has invalid schema
- **THEN** the pipeline fails fast with a clear error message (no silent fallback)

### Requirement: Auto Collect Previous-Day AI News
The system SHALL automatically collect AI-related news published on the previous day (relative to run date) from trusted sources.

#### Scenario: Successful auto collection
- **WHEN** auto mode runs on date D
- **THEN** only items with `published_at` in [D-1 00:00:00, D-1 23:59:59] are kept for downstream processing

#### Scenario: Non-AI item filtered out
- **WHEN** a collected item is not AI-related
- **THEN** it is filtered out before dedup/extraction and counted in the report

### Requirement: Report Includes Filtering Stats
The system SHALL include filtering statistics in `PipelineReport` and persisted report artifacts.

#### Scenario: Report contains filter counts
- **WHEN** pipeline finishes
- **THEN** report includes at least: fetched, after_time_filter, after_ai_filter, after_dedup

## MODIFIED Requirements
### Requirement: Source Fetching
Current: RSS fetching requires `--rss` arguments; without them it falls back to mock (when `--mock`) or empty input.
Modified: RSS fetching defaults to “auto mode” using the trusted source list; `--rss` remains for manual override; mock remains for offline tests.

## REMOVED Requirements
None.