# Grad Question Bank - 考研智能题库系统

智能题库管理 + 知识点掌握度分析工具，帮助考研学生精准定位薄弱环节。

## 功能特性

- **三级知识体系**：学科 -> 章节 -> 知识点，支持自定义扩展
- **AI 知识点分析**：支持 DeepSeek / 小米 MiMo / OpenAI 等多种 AI 服务商
- **AI 识图**：上传题目图片，AI 自动识别文字和公式，支持一张图多道题
- **浏览器端 OCR**：Tesseract.js 本地识别，无需后端调用
- **掌握度追踪**：三级标记（已掌握 / 模糊 / 完全不会）
- **薄弱环节统计**：按知识点聚合掌握度分布，加权计算薄弱排序
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

```bash
pip install flask requests
```

### 2. 启动应用

```bash
python app.py
```

浏览器打开 `http://127.0.0.1:5000` 即可使用。

### 3. 配置 AI（首次使用需配置）

1. 访问左侧菜单的「设置」页面
2. 选择 AI 服务商（DeepSeek / MiMo / OpenAI / 自定义）
3. 填入对应的 API Key，点击「测试连接」确认 OK
4. 保存设置

> API Key 存储在本地数据库中，不会上传到任何第三方。
> 每个服务商的 Key 独立存储，切换服务商不会互相覆盖。

## 项目结构

```
GradQuestionBank/
├── app.py              # Flask 主应用（REST API + 静态文件托管）
├── database.py         # 数据库建表、种子数据、自动迁移、工具函数
├── latex_utils.py      # LaTeX 清理工具
├── requirements.txt    # Python 依赖
├── data/
│   └── grad.db         # SQLite 数据库（运行后自动生成）
├── frontend/           # React + Vite 前端
│   ├── src/
│   │   ├── api.ts      # API 请求封装
│   │   ├── types.ts    # TypeScript 类型定义
│   │   ├── App.tsx     # 路由配置
│   │   ├── components/
│   │   │   └── Layout.tsx    # 布局组件（侧边栏导航）
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

## 预置学科

| 学科 | 章节数 | 知识点数 |
|------|--------|---------|
| 政治 | 5 | 20+ |
| 计算机408 | 4 | 24+ |

可在「学科管理」页面自由添加新学科、章节和知识点。

## License

MIT
