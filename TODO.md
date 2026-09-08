# Grad Question Bank - 考研智能题库系统

## 项目定位
题库管理 + 知识点掌握度分析系统。核心流程：
录入题目 -> AI分析知识点 -> 标记做题感受 -> 统计薄弱知识点

本项目是单机个人工具。当前阶段只完成题库导入、做题记录和知识点统计，不做登录、多用户隔离和复习计划。

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
- [x] 掌握度标记：五档做题感受
- [x] 统计仪表盘：Chart.js 图表 + 薄弱知识点排行
- [x] 题目列表题号显示（1, 2, 3...）
- [x] 做题记录页面（/practice）：来源筛选 + 搜索 + 拖拽批量选择 + 掌握度标记
- [x] 掌握度五档：知识盲区(1) / 只做了开头(2) / 易错细节(3) / 独立完成(4) / 轻松秒杀(5)
- [x] 概览页入口改为「添加做题记录」
- [x] 题目搜索 + 筛选 + 编辑
- [x] 批量录入 + 数据导入/导出（JSON）
- [x] 数据库自动迁移
- [x] 考试层级结构：考试类型（数学一/二/三、政治、408）→ 学科 → 章节 → 知识点
- [x] 考试管理页面（/exams）：关联/取消关联学科

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
- [x] React 前端各页面功能验证和 Bug 修复
  - [x] 数据库迁移：knowledge_points.parent_id 列
  - [x] API 端点：knowledge-tree, kps/merge, kps/move, kps/children, kps/parent
  - [x] ChapterDetail.tsx 树形渲染修复
- [x] 知识点树前端交互优化（拖拽移动、可视化编辑）
- [x] 题目来源管理（按 PDF 文件名筛选、标签显示、批量删除）

### 高优先级：知识点唯一来源

知识点管理中的条目是唯一标准。导入时只允许匹配已有知识点，不再因 LLM 输出自动创建新知识点；无法匹配的题目必须跳过并报告。

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
- [x] LLM 自动发现重复知识点（pipeline/canonical/kp_dedup.py）
- [x] 前端审核界面（/dedup 页面，查看/接受/拒绝重复建议）
- [x] 批量应用到别名系统（/api/kps/dedup/apply）
- [ ] 持续维护：定期运行 + 积累新别名

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
- [x] 前端：导入按钮 + 来源输入（支持历史来源快速填入）

### 题目来源管理
- [x] 题目列表增加「来源」筛选（按 PDF 文件名）
- [x] 题目列表增加来源标签显示
- [x] 支持按来源批量删除/编辑

### 本地模型集成
- [x] DeepSeek chat / LM Studio 本地 API 已集成
- [x] 设置页增加本地模型配置选项
- [x] PDF 导入来源编辑（统一来源 + 历史下拉）

### 远期
- [ ] Neon Postgres 数据库迁移
- [ ] 复习推荐算法（统计模块完成后再做）
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
| v2.5.0 | 2026-07-11 | 前端验证修复 + 知识点去重（LLM 自动检测 + 前端审核 + 别名批量应用） |
| v2.6.0 | 2026-07-11 | 考试层级结构 + 知识点树拖拽 + 题目来源管理 + PDF 导入来源编辑 |
| v2.7.0 | 2026-07-11 | 做题记录页面 + 题号显示 + 掌握度分级优化（已掌握/模糊/困难） |
| v2.8.0 | 2026-08-18 | 五档做题感受、薄弱统计、页码与视觉复判、逐页自动导入 |
| v2.9.0 | 2026-09-08 | 题目列表/做题记录页重构、题号搜索排序、批量管理、范围导出、LaTeX 详情渲染 |

---

## 已知问题
1. **Flask secret_key** — 未配置 FLASK_SECRET_KEY 时 session 不持久

## 当前验收任务

- [x] 五档掌握度和薄弱统计公式落地
- [x] `start.bat` 固定使用项目 `.venv` Python
- [x] DeepSeek `deepseek-v4-flash` chat 接入 PDF 流水线
- [x] PDF 导入统一使用设置页 LLM 路线（本地 LM Studio / API 可切换）
- [x] 逐题保留来源页码，题干缺失时自动把原 PDF 页面图片交给当前 LLM 路线视觉复判
- [x] 视觉复判失败保留题目并标记“待复核”
- [x] PDF 导入默认逐页处理并自动录入题库，完成后处理下一页
- [x] 设置页本地服务商显示为“本地部署”
- [x] 题目列表批量管理：全选、批量删除、批量来源
- [x] 导出题库支持全部 / 按学科 / 按章节，知识点仅包含范围内条目
- [x] 做题记录默认只看未标记，支持左键拖选、右键拖取消，勾选未标记默认“独立完成”
- [x] 已标记题目使用左侧色条与掌握度徽章区分
- [x] `p17-37.pdf` 文本路线恢复并导入 62 道题（0 跳过）
- [x] `p17-37.pdf` 合并结果保留 62 题的来源页码
- [x] 导入题目完成五档做题记录并验证知识点薄弱统计
- [x] 知识点导入只匹配管理中的已有条目（唯一同名条目允许跨章节回退）
