# Grad Question Bank - 项目文档

> 考研智能题库系统：题库管理 + AI 知识点分析 + 掌握度统计

---

## 项目概述

面向考研学生的智能题库管理系统。核心流程：

```
录入题目 -> AI 分析知识点 -> 用户审核/调整 -> 标记掌握情况 -> 统计薄弱环节
```

支持两种题目来源：
1. **手动录入**：文字 + 图片 + AI 识别
2. **PDF 批量导入**：PDF → MinerU → 规则引擎 → LLM → 题库

**GitHub 仓库：** https://github.com/zzz1423/GradQuestionBank

---

## 技术栈

| 层面 | 技术 | 说明 |
|------|------|------|
| 后端 | Python + Flask | REST API + 静态文件托管 |
| 前端 | React 19 + Vite + TypeScript | SPA 架构，Bootstrap 5 UI |
| 数据库 | SQLite | 单文件数据库 `data/grad.db` |
| 数学公式 | KaTeX | LaTeX 实时预览 |
| AI | DeepSeek / MiMo / OpenAI | 题目分析、知识点提取 |
| PDF 提取 | MinerU 3.4.2 | pipeline backend |
| LLM | Qwen 3.5 9B via LM Studio | 结构化输出，Pydantic 校验 |

---

## 快速启动

```bash
# 启动后端
python app.py

# 访问
# http://127.0.0.1:5000
```

---

## 项目结构

```
GradQuestionBank/
├── app.py                    # Flask 主应用
├── database.py               # 数据库建表、种子数据、迁移
├── latex_utils.py            # LaTeX 清理
│
├── pipeline/                 # PDF → 题库流水线
│   ├── __init__.py
│   ├── pipeline.py           # 流水线编排器（主入口）
│   ├── splitter.py           # 题目切分器
│   ├── splitter_llm.py       # LLM 分割 + 噪音过滤 + LaTeX 修复
│   ├── ocr_repair.py         # OCR 修复层（LLM 后处理）
│   ├── latex_fix.py          # LaTeX 定界符自动修复
│   ├── enricher.py           # 逐题 LLM 丰富（断点恢复）
│   ├── merger.py             # 合并器 → import_ready.json
│   ├── schema.py             # DOM 数据模型
│   ├── task_manager.py       # 后台任务管理（JSON 持久化）
│   ├── converters/
│   │   └── mineru_v2.py      # MinerU → NormalizedDocument
│   ├── detectors/
│   │   └── rule_engine.py    # 题目检测 + 边界检测
│   ├── renderers/
│   │   └── markdown.py       # NormalizedDocument → Markdown
│   └── llm/
│       ├── models.py          # Pydantic 数据模型
│       ├── split_models.py    # LLM 分割器输出模型
│       ├── prompt.py          # Prompt 构建器
│       ├── llm_client.py      # 通用 LLM 客户端（json_schema 支持）
│       ├── validator.py       # JSON 校验 + 重试 + 反斜杠修复
│       ├── extractor.py       # 单次调用入口（旧版）
│       └── schemas/           # JSON Schema（结构化输出）
│
├── frontend/                  # React + Vite 前端
│   └── src/
│       ├── pages/             # 页面组件
│       └── components/        # 通用组件
│
├── data/
│   ├── grad.db                # SQLite 数据库
│   └── pipeline-output/       # 流水线输出
│
└── docs/
    └── schema/
        └── document_object_model.md
```

---

## PDF 流水线架构

```
PDF
 ↓ MinerU CLI (-b pipeline)
Raw (content_list_v2.json)
 ↓ pipeline/converters/mineru_v2.py
NormalizedDocument
 ↓ pipeline/detectors/rule_engine.py
AnnotatedDocument
 ↓ pipeline/splitter_llm.py (LLM 分割 + 噪音过滤 + LaTeX 修复)
llm_split_result.json
 ↓ pipeline/splitter.py
questions/question_0001.json ...
 ↓ pipeline/ocr_repair.py (OCR 修复)
questions/question_0001.repaired.json ...
 ↓ pipeline/enricher.py (逐题 LLM，断点恢复)
questions/question_0001.enriched.json ...
 ↓ pipeline/merger.py
import_ready.json → /api/import → 题库数据库
```

### 设计原则
- **不可变**：每层产出新数据，不修改上一层
- **逐题处理**：每题独立 LLM 调用，支持断点恢复
- **中间文件保留**：方便调试和缓存
- **LLM 不含数据库 ID**：只输出业务数据
- **Pydantic 校验**：结构化输出，自动重试

---

## 数据库设计

```sql
subjects (id, name, created_at)
chapters (id, subject_id, name, sort_order, created_at)
knowledge_points (id, chapter_id, name, description, sort_order, parent_id, created_at)
questions (id, subject_id, content, answer, source, mastery_level, created_at, updated_at)
question_knowledge_points (question_id, knowledge_point_id, role, weight)
tags (id, name, created_at)
question_tags (question_id, tag_id)
settings (key, value)
```

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/subjects` | GET/POST | 学科管理 |
| `/api/subjects/<id>/chapters` | POST | 添加章节 |
| `/api/chapters/<id>/kps` | POST | 添加知识点 |
| `/api/questions` | GET/POST | 题目列表 / 添加题目 |
| `/api/questions/<id>/mastery` | POST | 标记掌握度 |
| `/api/analyze-question` | POST | AI 分析题目 |
| `/api/statistics` | GET | 统计数据 |
| `/api/export` | GET | 导出题库 |
| `/api/import` | POST | 导入题库 |
| `/api/settings` | GET/POST | AI 设置 |
| `/api/knowledge-tree` | GET | 获取知识点树（支持 subject_id/chapter_id 过滤） |
| `/api/kps/<id>/children` | GET | 获取子知识点 |
| `/api/kps/<id>/parent` | GET | 获取父知识点 |
| `/api/kps/move` | POST | 移动知识点到新父节点 |
| `/api/kps/merge` | POST | 合并两个知识点 |
| `/api/pdf/import` | POST | 上传 PDF 并启动流水线 |
| `/api/tasks` | GET | 列出所有任务 |
| `/api/tasks/<id>` | GET | 查询任务状态/进度 |
| `/api/tasks/<id>/result` | GET | 获取任务结果 |

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v1.0.0 | 2026-06-23 | 初始版本 |
| v1.1.0 | 2026-06-24 | 知识点分级、权重、tags |
| v1.1.2 | 2026-06-26 | CodeRabbit 修复 + LaTeX 清理 |
| v2.0.0 | 2026-07-01 | React + Vite 前端迁移 |
| v2.1.0 | 2026-07-01 | 多 AI 服务商、MiMo vision |
| v2.2.0 | 2026-07-10 | PDF 流水线（MinerU + 规则引擎 + LLM 结构化输出） |
| v2.3.0 | 2026-07-10 | LLM 分割器 + OCR 修复层 + LaTeX 修复 + JSON 结构化输出 + 进度追踪 |
| v2.4.0 | 2026-07-10 | 知识点树（父子关系、合并、移动）+ 数据库迁移 |

---

## 已知问题
1. **Flask secret_key** — 未配置时 session 不持久
2. **Turbomind/Blackwell** — lmdeploy 加速不可用，MinerU 使用 `-b pipeline`
