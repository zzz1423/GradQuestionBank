# Grad Question Bank - 考研智能题库系统

## 项目定位
题库管理 + 知识点掌握度分析系统。核心流程：
录入题目 → DeepSeek分析知识点 → 用户审核/调整 → 标记掌握情况 → 统计分析

## 技术栈
- 前端：Bootstrap 5 + Jinja2 + KaTeX
- 后端：Python + Flask
- 数据库：SQLite
- 图表：Chart.js
- AI：DeepSeek API
- 代码审查：CodeRabbit（通过 WSL 调用，代理有问题暂不可用）

## 插件依赖
| 插件 | 用途 | 状态 |
|------|------|------|
| build-web-apps | 前端 UI 重构至 React | 待启动 |
| neon-postgres | 数据库迁移至云端 | 待启动 |
| coderabbit | 代码质量审查 | 已用多轮，通过 WSL 调用（需代理） |

---

## 已完成功能

### 核心功能
- [x] Flask 应用框架 + SQLite 数据库
- [x] 预置种子数据（政治 5 章 20+ 知识点，计算机408 4 章 24+ 知识点）
- [x] 三级知识体系：学科 → 章节 → 知识点（完整 CRUD）
- [x] 题目录入：文字 + 图片上传 + AI 识别
- [x] LaTeX 支持：KaTeX 实时预览 + 文档清理功能
- [x] 知识点分级：主要/次要 + 权重 (0.1-1.0)
- [x] Tags 标签：从知识点自动生成
- [x] DeepSeek API 集成：分析知识点、权重、tags
- [x] API 响应缓存（避免重复调用）
- [x] 掌握度标记：已掌握 / 模糊 / 完全不会
- [x] 统计仪表盘：Chart.js 图表 + 薄弱知识点排行（加权计算）
- [x] 题目搜索 + 筛选（学科/章节/知识点/掌握度）
- [x] 题目编辑功能
- [x] 批量录入（用 --- 分隔多道题）
- [x] 数据导入/导出（JSON 格式，含 role/weight/tags）

### 代码质量
- [x] 多轮 CodeRabbit 审查，累计修复 15+ 个问题
- [x] .idea/ 加入 .gitignore
- [x] XSS 防护（escapeHtml）
- [x] SQL 注入防护（参数化查询）
- [x] 缓存 key 一致性修复
- [x] 原子性数据库提交

---

## 待办事项

### 近期
- [x] LaTeX 清理功能完善（支持 noindent/textbf/bigskip/section 等）
- [ ] DeepSeek API 实际测试（需配置 DEEPSEEK_API_KEY）
- [x] CodeRabbit WSL 调用正常（需代理 172.25.160.1:7890）

### 远期
- [ ] React + Vite 前端迁移
- [ ] Neon Postgres 数据库迁移（多用户场景再考虑）
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
| - | 2026-06-24 | LaTeX 文档清理、Tags 系统简化 |
| v1.1.2 | 2026-06-26 | CodeRabbit 审查 8 项修复 + LaTeX 清理增强 |

---

## 已知问题
1. ~~**LaTeX 清理** — 已修复，支持 noindent/textbf/bigskip/section 等常见 LaTeX 命令~~
2. ~~**CodeRabbit** — 已修复，通过 WSL 代理可正常调用~~
3. **Flask secret_key** — 未配置 FLASK_SECRET_KEY 时 session 不持久