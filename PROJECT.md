# Grad Question Bank - 项目文档

> 考研智能题库系统：题库管理 + AI 知识点分析 + 掌握度统计

---

## 项目概述

这是一个面向考研学生的智能题库管理系统。核心流程：

```
录入题目 → DeepSeek AI 分析知识点 → 用户审核/调整 → 标记掌握情况 → 统计薄弱环节
```

**GitHub 仓库：** https://github.com/zzz1423/GradQuestionBank

---

## 技术栈

| 层面 | 技术 | 说明 |
|------|------|------|
| 后端 | Python + Flask | REST API + 静态文件托管 |
| 前端 | React 19 + Vite + TypeScript | SPA 架构，Bootstrap 5 UI |
| 数据库 | SQLite | 单文件数据库，位于 `data/grad.db` |
| 图表 | Chart.js | 统计页面可视化 |
| 数学公式 | KaTeX | LaTeX 实时预览 |
| AI | DeepSeek API | 题目分析、知识点提取、标签建议 |
| 代码审查 | CodeRabbit CLI | 通过 WSL 调用 |

---

## 快速启动

```bash
# 1. 安装依赖
pip install flask requests flask-cors

# 2. 配置环境变量（可选，AI 功能需要）
set DEEPSEEK_API_KEY=your_api_key_here        # Windows CMD
$env:DEEPSEEK_API_KEY="your_api_key_here"     # PowerShell

# 3. 启动
python app.py

# 4. 访问
# http://127.0.0.1:5000
```

> 只需运行 `app.py`，Flask 同时托管 API 和前端静态文件。

---

## 项目结构

```
GradQuestionBank/
├── app.py                          # Flask 主应用（REST API + 静态文件托管）
├── database.py                     # 数据库建表、种子数据、自动迁移、工具函数
├── latex_utils.py                  # LaTeX 清理工具
├── requirements.txt                # Python 依赖
├── LICENSE                         # MIT 协议
├── README.md                       # 项目说明
├── TODO.md                         # 开发计划与进度记录
├── PROJECT.md                      # 本文档（项目详细信息）
│
├── data/
│   └── grad.db                     # SQLite 数据库（运行后自动生成）
│
├── frontend/                       # React + Vite 前端
│   ├── src/
│   │   ├── api.ts                  # API 请求封装
│   │   ├── types.ts                # TypeScript 类型定义
│   │   ├── App.tsx                 # 路由配置
│   │   ├── App.css                 # 侧边栏样式
│   │   ├── index.css               # 全局样式
│   │   ├── main.tsx                # 入口
│   │   ├── components/
│   │   │   └── Layout.tsx          # 布局组件（侧边栏导航）
│   │   └── pages/
│   │       ├── Dashboard.tsx       # 首页概览
│   │       ├── Subjects.tsx        # 学科管理
│   │       ├── SubjectDetail.tsx   # 章节管理
│   │       ├── ChapterDetail.tsx   # 知识点管理
│   │       ├── Questions.tsx       # 题目列表（筛选+搜索）
│   │       ├── QuestionDetail.tsx  # 题目详情+掌握度标记
│   │       ├── AddQuestion.tsx     # 录入题目（图片+LaTeX+AI）
│   │       ├── EditQuestion.tsx    # 编辑题目
│   │       ├── ReviewKnowledge.tsx # 知识点审核
│   │       ├── BatchImport.tsx     # 批量录入
│   │       └── Statistics.tsx      # 统计仪表盘
│   ├── dist/                       # 构建产物（Flask 托管此目录）
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
└── templates/                      # 旧版 Jinja2 模板（已废弃，保留备用）
```

---

## 架构说明

```
浏览器 → http://127.0.0.1:5000
  │
  ├─ /api/*  → Flask REST API（JSON 响应）
  ├─ /assets/* → 前端静态资源（JS/CSS/字体）
  └─ /*      → index.html（SPA 路由，React Router 接管）
```

- 后端是纯 REST API，返回 JSON
- 前端是 React SPA，通过 Vite 构建后由 Flask 托管
- 开发时可单独运行 `pnpm dev`（端口 3000，代理到 5000）
- 生产部署只需运行 `python app.py`

---

## 数据库设计

### 核心表

```sql
-- 学科
subjects (id, name, created_at)

-- 章节
chapters (id, subject_id → subjects, name, sort_order, created_at)

-- 知识点
knowledge_points (id, chapter_id → chapters, name, description, sort_order, created_at)

-- 题目
questions (id, subject_id → subjects, content, answer, source, mastery_level, created_at, updated_at)

-- 题目-知识点关联（含 role 和 weight）
question_knowledge_points (question_id → questions, knowledge_point_id → knowledge_points, role, weight)
-- role: 'primary' | 'secondary'
-- weight: 0.1 ~ 1.0

-- 标签
tags (id, name, created_at)

-- 题目-标签关联
question_tags (question_id → questions, tag_id → tags)

-- API 缓存
api_cache (id, content_hash, subject_name, response_json, created_at)
```

### 自动迁移

`database.py` 包含 `_migrate()` 函数，启动时自动检查并添加缺失的列。目前迁移项：
- `question_knowledge_points.role`（TEXT，默认 'primary'）
- `question_knowledge_points.weight`（REAL，默认 1.0）

---

## API 端点

### REST API（全部返回 JSON）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/constants` | GET | 常量（掌握度标签、颜色） |
| `/api/dashboard` | GET | 首页统计数据 + 最近题目 |
| `/api/subjects` | GET/POST | 学科列表 / 添加学科 |
| `/api/subjects/<id>` | GET/DELETE | 学科详情 / 删除学科 |
| `/api/subjects/<id>/chapters` | POST | 添加章节 |
| `/api/chapters/<id>` | GET/DELETE | 章节详情 / 删除章节 |
| `/api/chapters/<id>/kps` | POST | 添加知识点 |
| `/api/kps/<id>` | DELETE | 删除知识点 |
| `/api/questions` | GET | 题目列表（支持筛选参数） |
| `/api/questions` | POST | 添加题目 |
| `/api/questions/batch` | POST | 批量录入 |
| `/api/questions/<id>` | GET/PUT/DELETE | 题目详情 / 编辑 / 删除 |
| `/api/questions/<id>/mastery` | POST | 标记掌握度 |
| `/api/questions/<id>/review` | GET/POST | 知识点审核 / 保存关联 |
| `/api/analyze-question` | POST | AI 分析题目（图片+文字） |
| `/api/analyze` | POST | AI 分析（纯文字） |
| `/api/statistics` | GET | 统计数据 |
| `/api/export` | GET | 导出题库（JSON 下载） |
| `/api/import` | POST | 导入题库（JSON） |

---

## 配置说明

### 环境变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | 否（AI功能必需） | DeepSeek API 密钥 |
| `FLASK_SECRET_KEY` | 否 | Flask session 密钥 |
| `NEON_DATABASE_URL` | 否 | PostgreSQL 连接字符串（不设置则用 SQLite） |

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v1.0.0 | 2026-06-23 | 初始版本：Flask + SQLite + Bootstrap，预置种子数据 |
| v1.0.1 | 2026-06-23 | 搜索、编辑、知识点审核优化 |
| v1.0.2 | 2026-06-24 | CodeRabbit 审查修复、批量录入、API 缓存 |
| v1.1.0 | 2026-06-24 | 知识点分级（primary/secondary）、权重系统、tags |
| v1.1.1 | 2026-06-24 | 图片上传、AI 题目识别、LaTeX 预览 |
| v1.1.2 | 2026-06-26 | CodeRabbit 审查修复 + LaTeX 清理增强 |
| v2.0.0 | 2026-07-01 | React + Vite 前端迁移、REST API 重构、数据库自动迁移 |

---

## 已知问题

1. **Flask secret_key** — 未配置 FLASK_SECRET_KEY 时 session 不持久
2. **LaTeX 清理** — JS 端正则转义有小问题，多数情况可用

## 注意事项

1. **数据库位置**：`data/grad.db`，备份只需复制此文件
2. **前端构建**：修改前端代码后需在 `frontend/` 目录运行 `pnpm build`
3. **种子数据**：首次运行自动写入政治和408，已有数据时不会重复写入
4. **API 缓存**：`api_cache` 表存储 AI 分析结果，避免重复调用
5. **图片上传**：图片转 base64 发送给 DeepSeek，不存储原图
6. **LaTeX 语法**：行内公式 `$...$`，独立公式 `$$...$$`
7. **批量录入**：题目间用 `---` 分隔，答案格式 `答案：X`
8. **Tags** — 从知识点名称自动生成，不需要手动输入
9. **知识点权重** — 主要知识点通常 0.8-1.0，次要 0.1-0.5
