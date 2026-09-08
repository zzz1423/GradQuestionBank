# Grad Question Bank - 考研智能题库系统

智能题库管理 + 知识点掌握度分析工具，帮助考研学生精准定位薄弱环节。

## 功能特性

- **三级知识体系**：学科 -> 章节 -> 知识点，支持自定义扩展
- **AI 知识点分析**：支持 DeepSeek / 小米 MiMo / OpenAI 等多种 AI 服务商
- **AI 识图**：上传题目图片，AI 自动识别文字和公式，支持一张图多道题
- **浏览器端 OCR**：Tesseract.js 本地识别，无需后端调用
- **做题记录**：勾选已完成题目，并记录五档做题感受
- **掌握度追踪**：知识盲区 / 只做了开头 / 易错细节 / 独立完成 / 轻松秒杀
- **薄弱环节统计**：按知识点和关联权重聚合，知识盲区额外加重
- **PDF 逐页导入**：MinerU 文本提取 + LLM 知识点分析，题干缺失时用原页视觉复判，按页自动录入
- **LLM 双路线**：本地 LM Studio 与在线 API 可在设置页切换，统一用于切题、知识点提取和视觉复判
- **题库管理**：按题号搜索/排序，支持学科/章节/来源/掌握度筛选，批量改来源与批量删除
- **按范围导出**：全部、按学科或按章节导出，导出内容只包含范围内知识点
- **LaTeX 支持**：KaTeX 实时预览，支持 $...$、$$...$$、\(...\)、\[...\] 四种格式
- **数据导入导出**：JSON 格式，方便备份和迁移
- **预置数据**：内置「政治」和「计算机408」的完整知识点骨架

## 技术栈

- **后端**：Python + Flask（REST API + 静态文件托管）
- **前端**：React 19 + Vite + TypeScript + Bootstrap 5
- **数据库**：SQLite（单文件，备份只需复制 `data/grad.db`）
- **图表**：Chart.js
- **数学公式**：KaTeX
- **AI**：DeepSeek / 小米 MiMo / OpenAI 兼容 API
- **OCR**：Tesseract.js（浏览器端）

## 快速开始

### 1. 安装依赖

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 启动应用

```powershell
.venv\Scripts\python.exe app.py
```

浏览器打开 `http://127.0.0.1:5000` 即可使用。

也可以直接双击项目根目录的 `start.bat`，它会固定使用项目 `.venv` 中的 Python。

### 3. 配置 AI（首次使用需配置）

1. 访问左侧菜单的「设置」页面
2. 选择“本地部署”或在线 API（DeepSeek / MiMo / OpenAI / 自定义）
3. 使用在线 API 时填入对应 Key，点击「测试连接」确认 OK
4. 保存设置

> API Key 存储在本地数据库中，不会上传到任何第三方。
> 每个服务商的 Key 独立存储，切换服务商不会互相覆盖。

PDF 导入统一使用设置页选择的 LLM 路线：

- **本地**：LM Studio 的 `qwen/qwen3.5-9b`，适合扫描件和公式 OCR 丢失的页面。
- **API**：DeepSeek 等在线服务，适合无需本地推理资源的日常导入。

流水线先做 MinerU 文本提取，再逐题保留来源页码并提取知识点。若某题题干缺失或不完整，系统会把该题所在原 PDF 页面渲染成图片，交给当前选择的 LLM 路线进行视觉复判；复判失败则保留题目并标记“待复核”。

默认启用“逐页处理并自动录入”：每完成一页的题目提取、知识点分析和视觉复判后，立即标好题号写入题库，再处理下一页。

## 当前验收

- `p17-37.pdf` 逐页流水线恢复并导入 62 道题（0 跳过），每题保留来源页码。
- 每道题至少关联一个知识点管理中已有的知识点，不自动创建无法匹配的条目。
- 导入后可用做题记录页完成五档掌握度标记，并在统计页查看薄弱知识点。
- 题目详情支持 KaTeX 渲染；题库管理、按题号搜索/排序、批量来源/删除、按学科/章节导出均已落地。

## 项目结构

```text
GradQuestionBank/
├── app.py              # Flask 主应用（REST API + 静态文件托管）
├── database.py         # 数据库建表、种子数据、自动迁移、工具函数
├── latex_utils.py      # LaTeX 清理工具
├── requirements.txt    # Python 依赖
├── data/
│   └── grad.db         # SQLite 数据库（运行后自动生成）
├── pipeline/           # PDF → JSON 流水线（逐页导入/视觉复判）
├── frontend/           # React + Vite 前端
│   ├── src/
│   │   ├── api.ts      # API 请求封装
│   │   ├── types.ts    # TypeScript 类型定义
│   │   ├── App.tsx     # 路由配置
│   │   ├── components/
│   │   │   ├── Layout.tsx    # 布局组件（侧边栏导航）
│   │   │   └── LatexContent.tsx  # KaTeX 内容渲染
│   │   └── pages/      # 各页面组件
│   └── dist/           # 构建产物（Flask 托管此目录）
├── templates/          # 旧版模板（已废弃，保留备用）
├── TODO.md             # 开发计划与进度
├── PROJECT.md          # 项目详细文档
└── README.md           # 本文件
```

## 数据备份

数据库文件位于 `data/grad.db`，备份只需复制此文件。恢复时将文件放回 `data/` 目录即可。

也可以通过侧边栏的「导出题库」功能将数据导出为 JSON 文件。

## 预置大纲

首次启动会自动载入 `data/exam_syllabus/` 下的数学一、数学二、数学三与 408 大纲，作为知识点管理的基础。可在「知识点管理」页面自由扩展学科、章节和知识点。

## License

MIT
