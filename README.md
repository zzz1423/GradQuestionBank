# Grad Question Bank - 考研智能题库系统

智能题库管理 + 知识点掌握度分析工具，帮助考研学生精准定位薄弱环节。

## 功能特性

- **三级知识体系**：学科 → 章节 → 知识点，支持自定义扩展
- **AI 知识点分析**：录入题目后调用 DeepSeek API 自动分析涉及的知识点，用户可审核调整
- **掌握度追踪**：三级标记（已掌握 / 模糊 / 完全不会）
- **薄弱环节统计**：按知识点聚合掌握度分布，自动排序薄弱知识点
- **可视化图表**：掌握度分布饼图、学科对比柱状图
- **数据导入导出**：JSON 格式，方便备份和迁移
- **预置数据**：内置「政治」和「计算机408」的完整知识点骨架

## 技术栈

- **后端**：Python + Flask
- **数据库**：SQLite（单文件，备份只需复制 `data/grad.db`）
- **前端**：HTML + Bootstrap 5 + Jinja2
- **图表**：Chart.js
- **AI**：DeepSeek API

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 DeepSeek API（可选）

设置环境变量以启用 AI 知识点分析功能：

```bash
# Windows
set DEEPSEEK_API_KEY=your_api_key_here

# Linux/Mac
export DEEPSEEK_API_KEY=your_api_key_here
```

### 3. 启动应用

```bash
python app.py
```

浏览器打开 `http://127.0.0.1:5000` 即可使用。

## 项目结构

```
GradQuestionBank/
├── app.py              # Flask 主应用（路由与业务逻辑）
├── database.py         # 数据库建表、种子数据、工具函数
├── requirements.txt    # Python 依赖
├── data/
│   └── grad.db         # SQLite 数据库（运行后自动生成）
├── templates/
│   ├── base.html              # 布局模板（侧边栏导航）
│   ├── index.html             # 首页概览
│   ├── subjects.html          # 学科管理
│   ├── subject_detail.html    # 章节管理
│   ├── chapter_detail.html    # 知识点管理
│   ├── questions.html         # 题目列表（支持筛选）
│   ├── add_question.html      # 录入题目
│   ├── question_detail.html   # 题目详情 + 掌握度标记
│   ├── review_knowledge.html  # 知识点审核（AI 分析）
│   └── statistics.html        # 统计仪表盘
└── TODO.md             # 开发计划
```

## 数据备份

数据库文件位于 `data/grad.db`，备份只需复制此文件。恢复时将文件放回 `data/` 目录即可。

也可以通过侧边栏的「导出题库」功能将数据导出为 JSON 文件。

## 预置学科

| 学科 | 章节数 | 知识点数 |
|------|--------|---------|
| 政治 | 5 | 20+ |
| 计算机408 | 4 | 24+ |

可在「学科管理」页面自由添加新学科、章节和知识点。

## License

MIT
