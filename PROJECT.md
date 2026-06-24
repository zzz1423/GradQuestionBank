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
| 后端 | Python + Flask | Web 框架，提供页面渲染和 JSON API |
| 数据库 | SQLite | 单文件数据库，位于 `data/grad.db` |
| 前端 | Bootstrap 5 + Jinja2 | 服务端渲染模板 |
| 图表 | Chart.js | 统计页面可视化 |
| 数学公式 | KaTeX | LaTeX 实时预览 |
| AI | DeepSeek API | 题目分析、知识点提取、标签建议 |
| 代码审查 | CodeRabbit CLI | 通过 WSL 调用 |

---

## 快速启动

```bash
# 1. 安装依赖
pip install flask requests

# 2. 配置环境变量（可选，AI 功能需要）
set DEEPSEEK_API_KEY=your_api_key_here        # Windows CMD
$env:DEEPSEEK_API_KEY="your_api_key_here"     # PowerShell
export FLASK_SECRET_KEY=your_secret_key       # 可选，不设置会每次重启丢失 session

# 3. 启动
python app.py

# 4. 访问
# http://127.0.0.1:5000
```

---

## 项目结构

```
GradQuestionBank/
├── app.py                          # Flask 主应用（所有路由和业务逻辑）
├── database.py                     # 数据库建表、种子数据、工具函数
├── requirements.txt                # Python 依赖（flask, requests）
├── LICENSE                         # MIT 协议
├── README.md                       # 项目说明
├── TODO.md                         # 开发计划与进度记录
├── PROJECT.md                      # 本文档（项目详细信息）
│
├── data/
│   └── grad.db                     # SQLite 数据库（运行后自动生成）
│
└── templates/                      # Jinja2 HTML 模板
    ├── base.html                   # 布局模板（侧边栏导航）
    ├── index.html                  # 首页概览
    ├── subjects.html               # 学科管理列表
    ├── subject_detail.html         # 章节管理
    ├── chapter_detail.html         # 知识点管理
    ├── questions.html              # 题目列表（筛选+搜索）
    ├── add_question.html           # 录入题目（图片上传+LaTeX预览+AI分析）
    ├── edit_question.html          # 编辑题目
    ├── question_detail.html        # 题目详情+掌握度标记
    ├── review_knowledge.html       # 知识点审核（AI分析结果+手动调整）
    ├── batch_import.html           # 批量录入
    └── statistics.html             # 统计仪表盘
```

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

### 掌握度等级

| 值 | 含义 | 颜色 |
|----|------|------|
| 0 | 未标记 | 灰色 |
| 1 | 完全不会 | 红色 |
| 2 | 模糊 | 黄色 |
| 3 | 已掌握 | 绿色 |

### 知识点权重系统

- **主要知识点（primary）**：权重通常 0.8-1.0，表示题目主要考察的内容
- **次要知识点（secondary）**：权重通常 0.1-0.5，表示题目涉及但非重点的内容
- **统计公式**：`知识点掌握度 = Σ(相关题目的掌握度 × 权重) / Σ(权重)`

### 预置种子数据

首次运行自动写入：

**政治（5 章，20+ 知识点）：**
- 马克思主义基本原理（唯物论、唯物辩证法、认识论、唯物史观、剩余价值理论...）
- 毛中特（毛泽东思想、邓小平理论、三个代表、科学发展观、习近平新时代...）
- 中国近现代史纲要（旧民主主义革命、新民主主义革命、社会主义改造、改革开放...）
- 思想道德与法治（人生观与价值观、社会主义核心价值观、道德修养、法治思维...）
- 形势与政策（国内形势、国际形势）

**计算机408（4 章，24+ 知识点）：**
- 数据结构（线性表、栈和队列、串、树与二叉树、图、查找、排序）
- 计算机组成原理（数据的表示和运算、存储器层次结构、指令系统、CPU、总线、I/O）
- 操作系统（概述、进程管理、内存管理、文件管理、I/O管理）
- 计算机网络（体系结构、物理层、数据链路层、网络层、传输层、应用层）

---

## API 端点

### 页面路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页概览 |
| `/subjects` | GET | 学科管理列表 |
| `/subjects/add` | POST | 添加学科 |
| `/subjects/<id>/delete` | POST | 删除学科 |
| `/subjects/<id>` | GET | 学科详情（章节列表） |
| `/subjects/<id>/chapters/add` | POST | 添加章节 |
| `/chapters/<id>/delete` | POST | 删除章节 |
| `/chapters/<id>` | GET | 章节详情（知识点列表） |
| `/chapters/<id>/kp/add` | POST | 添加知识点 |
| `/kp/<id>/delete` | POST | 删除知识点 |
| `/questions` | GET | 题目列表（支持 subject_id, chapter_id, kp_id, mastery, search 筛选） |
| `/questions/add` | GET/POST | 录入题目（支持图片上传） |
| `/questions/batch` | GET/POST | 批量录入 |
| `/questions/<id>` | GET | 题目详情 |
| `/questions/<id>/edit` | GET/POST | 编辑题目 |
| `/questions/<id>/delete` | POST | 删除题目 |
| `/questions/<id>/mastery` | POST | 标记掌握度 |
| `/questions/<id>/review` | GET/POST | 知识点审核（AI分析+手动调整） |
| `/statistics` | GET | 统计仪表盘 |
| `/api/export` | GET | 导出题库（JSON） |
| `/api/import` | POST | 导入题库（JSON） |

### API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/analyze` | POST | 分析题目知识点（旧版，基于文字） |
| `/api/analyze-question` | POST | 分析题目（支持图片+文字，返回 LaTeX + KP + tags） |

#### `/api/analyze-question` 请求格式

```json
{
  "content": "题目文字内容（可选）",
  "image": "data:image/png;base64,...（可选）",
  "subject_name": "学科名称"
}
```

#### `/api/analyze-question` 响应格式

```json
{
  "content": "题目原始文字",
  "latex_content": "LaTeX 格式题目",
  "answer": "答案",
  "knowledge_points": [
    {"name": "概率论", "role": "primary", "weight": 1.0, "is_new": false},
    {"name": "导数应用", "role": "secondary", "weight": 0.3, "is_new": true, "chapter": "高等数学"}
  ],
  "tags": ["计算题", "概率分布"]
}
```

---

## 核心功能

### 1. 题目录入
- **手动录入**：选择学科 → 填写题干（支持 LaTeX）→ 填写答案
- **图片识别**：拖拽/上传图片 → AI 自动识别题目 → 返回 LaTeX 格式
- **批量录入**：一次粘贴多道题，用 `---` 分隔，自动提取答案
- **KaTeX 预览**：输入时实时渲染数学公式

### 2. AI 知识点分析
- 调用 DeepSeek API 分析题目
- 自动建议知识点（含 primary/secondary 分类和权重）
- 自动建议标签（tags）
- 用户可审核、调整、补充
- API 响应自动缓存，相同题目不重复调用

### 3. 知识点体系管理
- 三级结构：学科 → 章节 → 知识点
- 完整 CRUD（增删改查）
- 预置政治和计算机408种子数据

### 4. 掌握度追踪
- 三级掌握度：已掌握 / 模糊 / 完全不会
- 加权统计：主要知识点权重高，次要知识点权重低
- 按钮一键标记

### 5. 统计分析
- 掌握度分布饼图
- 按学科掌握度柱状图
- 薄弱知识点排行榜（加权计算）
- 进度条可视化

### 6. 数据管理
- JSON 格式导入/导出
- 导出包含：题目、知识点关联（含 role/weight）、tags、掌握度
- 侧边栏一键操作

---

## 配置说明

### 环境变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | 否（AI功能必需） | DeepSeek API 密钥 |
| `FLASK_SECRET_KEY` | 否 | Flask session 密钥，不设置则每次重启丢失 session |

### DeepSeek API

- 端点：`https://api.deepseek.com/chat/completions`
- 模型：`deepseek-chat`（图片识别可能需要 `deepseek-vision`）
- 温度：0.3（低温度，稳定输出）
- 超时：30-60 秒

---

## 数据备份

**方法 1：复制数据库文件**
```
data/grad.db → 备份到任意位置
```

**方法 2：使用导出功能**
- 侧边栏点击"导出题库"
- 下载 JSON 文件
- 可通过"导入题库"恢复

---

## 代码审查

使用 CodeRabbit CLI（通过 WSL 调用）：

```bash
wsl -d Ubuntu-24.04 bash -c "cd /mnt/e/Temp/CCC/Codex/GradQuestionBank && /root/.local/bin/coderabbit review --agent"
```

已发现并修复的问题（累计 15+）：
- `.idea/` IDE 配置泄露（已加入 .gitignore）
- SQL 参数顺序错误
- 缓存 key 不一致
- XSS 防护缺失
- 导出缺少 role/weight/tags
- Flask secret_key 不持久
- 非原子性数据库提交

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v1.0.0 | 2026-06-23 | 初始版本：Flask + SQLite + Bootstrap，预置种子数据 |
| v1.0.1 | 2026-06-23 | 搜索、编辑、知识点审核优化 |
| v1.0.2 | 2026-06-24 | CodeRabbit 审查修复、批量录入、API 缓存 |
| v1.1.0 | 2026-06-24 | 知识点分级（primary/secondary）、权重系统、tags |
| v1.1.1 | 2026-06-24 | 图片上传、AI 题目识别、LaTeX 预览、CodeRabbit 修复 |
| - | 2026-06-24 | LaTeX 文档清理、Tags 系统简化（从知识点自动生成） |

---

## 待办事项

### 近期
- [ ] Neon Postgres 数据库迁移
- [ ] React + Vite 前端迁移
- [ ] 复习推荐算法

### 远期
- [ ] 用户登录系统
- [ ] 题目难度评估
- [ ] 错题本功能
- [ ] 学习计划生成
- [ ] 移动端适配优化

---

## 已知问题

1. **LaTeX 清理** — 用户反馈清理后仍有渲染问题，需要进一步调试
2. **CodeRabbit** — WSL 网络代理配置问题，暂时无法使用
3. **Flask secret_key** — 未配置 FLASK_SECRET_KEY 时 session 不持久

## 注意事项

1. **数据库位置**：`data/grad.db`，备份只需复制此文件
2. **种子数据**：首次运行自动写入政治和408，已有数据时不会重复写入
3. **API 缓存**：`api_cache` 表存储 AI 分析结果，避免重复调用
4. **图片上传**：图片转 base64 发送给 DeepSeek，不存储原图
5. **LaTeX 语法**：行内公式 `$...$`，独立公式 `$$...$$`
6. **批量录入**：题目间用 `---` 分隔，答案格式 `答案：X`
7. **Tags** — 从知识点名称自动生成，不需要手动输入
8. **知识点权重** — 主要知识点通常 0.8-1.0，次要 0.1-0.5
