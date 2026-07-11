# Grad Question Bank - 考研智能题库系统

## 项目定位
题库管理 + 知识点掌握度分析系统。核心流程：
录入题目 -> AI分析知识点 -> 用户审核/调整 -> 标记掌握情况 -> 统计分析

## 技术栈
- 前端：React 19 + Vite + TypeScript + Bootstrap 5 + KaTeX + Chart.js
- 后端：Python + Flask（REST API + 静态文件托管）
- 数据库：SQLite（支持迁移至 PostgreSQL）
- AI：DeepSeek API / 小米 MiMo API / OpenAI 兼容
- PDF 提取：MinerU 3.4.2（pipeline backend）
- LLM：Qwen 3.5 9B via LM Studio（http://127.0.0.1:1234/v1）

---

## 已完成功能

### 核心功能
- [x] Flask REST API 后端 + SQLite 数据库
- [x] React + Vite 前端（SPA 架构，TypeScript）
- [x] Flask 直接托管前端静态文件（单服务器运行）
- [x] 预置种子数据（政治5章 20+ 知识点，计算机408 4章 24+ 知识点）
- [x] 三级知识体系：学科 -> 章节 -> 知识点（完整 CRUD）
- [x] 题目录入：文字 + 图片上传 + AI 识别
- [x] LaTeX 支持：KaTeX 实时预览 + 文档清理功能
- [x] 知识点分级：主要/次要 + 权重 (0.1-1.0)
- [x] Tags 标签：从知识点自动生成
- [x] AI 题目分析：知识点提取、权重、tags
- [x] 掌握度标记：已掌握 / 模糊 / 完全不会
- [x] 统计仪表盘：Chart.js 图表 + 薄弱知识点排行
- [x] 题目搜索 + 筛选 + 编辑
- [x] 批量录入 + 数据导入/导出（JSON）
- [x] 数据库自动迁移

### AI 功能（v2.1.0）
- [x] 多 AI 服务商支持：DeepSeek / MiMo / OpenAI / 自定义
- [x] 网页端 API Key 配置
- [x] AI 识图：MiMo vision 模型
- [x] 多题目图片识别：批量预览/编辑/保存

### PDF 流水线（pipeline/）
- [x] MinerU 迁移：从 magic-pdf 1.x 迁移至官方 MinerU 3.4.2
- [x] DOM Schema v1.0.0（`pipeline/schema.py`）
- [x] Layer 1: MinerU CLI（`-b pipeline`）
- [x] Layer 2: NormalizedDocument Converter（`pipeline/converters/mineru_v2.py`）
- [x] Layer 3: Question Detection 规则引擎（`pipeline/detectors/rule_engine.py`）
  - 8/8 题目检测 + 8/8 边界检测（1-3.pdf）
  - 10 种噪声过滤模式
- [x] Layer 4+5: LLM 结构化输出（`pipeline/llm/`）
  - Pydantic 数据模型（QuestionCollection, Question, KnowledgePoint）
  - 通用 OpenAI 兼容客户端（LM Studio / Ollama / OpenAI / vLLM）
  - JSON 校验 + 自动重试
  - 8/8 题目知识点提取成功
- [x] 工业级 Pipeline 编排（`pipeline/pipeline.py`）
  - 逐题切分（`pipeline/splitter.py`）
  - 逐题 LLM 丰富（`pipeline/enricher.py`）
  - 断点恢复：中断后自动跳过已完成步骤
  - 中间文件保留：`questions/*.json` + `*.enriched.json`
  - 合并器（`pipeline/merger.py`）→ import_ready.json

---

## 待办事项

### 近期
- [ ] React 前端各页面功能验证和 Bug 修复
- [ ] 知识点树前端交互优化（拖拽移动、可视化编辑）
- [ ] 题目来源管理（按 PDF 文件名筛选、标签显示、批量删除）

### 高优先级：知识点规范化（Knowledge Point Canonicalization）

LLM 提取的知识点名称不统一（如 "函数极限"/"极限"/"求极限"/"极限计算" 指同一概念），
必须在导入数据库前规范化，否则数据库将出现大量重复知识点。

#### Phase 1（高优先级）
- [x] 设计知识点标准名称（Canonical Name）机制（pipeline/canonical/kp_canonical.py）
- [x] 建立知识点别名（Alias）映射表（pipeline/canonical/kp_aliases.json）
- [x] 支持多个别名映射到同一个标准知识点
- [x] 设计知识点唯一标识（数据库自增 ID + 标准名称作为逻辑标识）
- [x] 导入数据库前完成知识点规范化（merger.py + app.py import 端点）

#### Phase 2
- [x] 建立知识点层级（章节 → 知识点）— data/exam_syllabus/ 数一/数二/数三 + 408 完整大纲
- [x] Subject-filtered KP hierarchy（按学科过滤知识点层级）
- [x] 支持知识点树（Knowledge Tree）— parent_id 自引用外键
- [x] 支持父子关系 — API: /api/knowledge-tree, /api/kps/<id>/children
- [x] 支持知识点合并与拆分 — API: /api/kps/merge, /api/kps/move

#### Phase 3
- [ ] 利用 Embedding + LLM 自动发现重复知识点
- [ ] 人工审核后更新 Alias 映射
- [ ] 构建持续维护的知识点词典

**设计原则：**
- LLM 不负责生成数据库 ID
- LLM 仅输出业务知识点名称
- 数据库统一维护标准知识点及别名
- 统计、查询、推荐均基于标准知识点

### PDF 流水线后续
- [x] 更多 PDF 格式验证（教材、考研真题、扫描版）— 已测试 1-3.pdf, p46.pdf, p6-7.pdf, p51-52.pdf
- [x] 后端 API：封装流水线为 Flask 端点（POST /api/pdf/import）
- [x] 前端：侧边栏新增「PDF导入」入口
- [x] 前端：PDF上传 + 提取结果预览（LaTeX 渲染、知识点确认）

### 题目来源管理
- [ ] 题目列表增加「来源」筛选（按 PDF 文件名）
- [ ] 题目列表增加来源标签显示
- [ ] 支持按来源批量删除/编辑

### 本地模型集成
- [x] LM Studio 本地 API 已集成（qwen/qwen3.5-9b）
- [ ] 设置页增加本地模型配置选项

### 远期
- [ ] Neon Postgres 数据库迁移
- [ ] 复习推荐算法
- [ ] 用户登录系统
- [ ] 移动端适配

---

## 版本历史
| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.0.0 | 2026-06-23 | 初始版本：Flask + SQLite + Bootstrap |
| v1.0.1 | 2026-06-23 | 搜索、编辑、知识点审核优化 |
| v1.0.2 | 2026-06-24 | CodeRabbit 审查修复、批量录入、API 缓存 |
| v1.1.0 | 2026-06-24 | 知识点分级（primary/secondary）、权重、tags |
| v1.1.1 | 2026-06-24 | 图片上传、AI 题目识别、LaTeX 预览 |
| v1.1.2 | 2026-06-26 | CodeRabbit 审查 8 项修复 + LaTeX 清理增强 |
| v2.0.0 | 2026-07-01 | React + Vite 前端迁移、REST API 重构、数据库自动迁移 |
| v2.1.0 | 2026-07-01 | 多 AI 服务商、MiMo vision、多题目识别、设置页面 |
| v2.2.0 | 2026-07-10 | PDF 流水线：MinerU + 规则引擎 + LLM 结构化输出 + 工业级 Pipeline |
| v2.3.0 | 2026-07-10 | LLM 分割器 + OCR 修复层 + LaTeX 修复 + JSON 结构化输出 + 进度追踪 |
| v2.4.0 | 2026-07-10 | 知识点树（父子关系、合并、移动）+ 数据库迁移 |

---

## 已知问题
1. **Flask secret_key** — 未配置 FLASK_SECRET_KEY 时 session 不持久
