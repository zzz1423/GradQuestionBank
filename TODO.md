# Grad Question Bank - 考研智能题库系统

## 项目定位
题库管理 + 知识点掌握度分析系统。核心流程：
录入题目 → DeepSeek分析知识点 → 用户审核/调整 → 标记掌握情况 → 统计分析

## 技术栈
- 前端：Bootstrap 5（已实现），后续迁移至 React + Vite（**build-web-apps** 插件）
- 后端：Python + Flask
- 数据库：SQLite（已实现），后续迁移至 Neon Postgres（**neon-postgres** 插件）
- 图表：Chart.js
- AI：DeepSeek API（知识点分析）
- 代码审查：CodeRabbit（**coderabbit** 插件）

## 插件依赖
| 插件 | 用途 | 触发时机 |
|------|------|---------|
| build-web-apps | 前端 UI 重构至 React | Phase 1 前端迁移 |
| neon-postgres | 数据库迁移至云端 | Phase 1 数据库迁移 |
| coderabbit | 代码质量审查 | Phase 5 |

## 数据设计
- 三级结构：学科 → 章节 → 知识点
- 掌握度三级：已掌握 / 模糊 / 完全不会
- 题目只存题干（含选项文字）+ 结果答案
- 预置政治、计算机408的基础知识点骨架，用户可自行扩展

---

## Phase 1 - 项目骨架与基础设施
- [x] 初始化 Flask 项目结构
- [x] SQLite 数据库建表 + 预置种子数据（政治 + 计算机408）
- [x] 基础页面布局（Bootstrap 5 侧边栏导航 + 10 个模板页面）
- [x] v1.0.0 发布至 GitHub
- [ ] 前端迁移至 React + Vite（待 build-web-apps 插件介入）
- [ ] 数据库迁移至 Neon Postgres（待 neon-postgres 插件介入）

## Phase 2 - 学科知识体系管理
- [x] 后端 API：学科/章节/知识点 CRUD
- [x] 学科管理页面
- [x] 章节管理页面
- [x] 知识点管理页面

## Phase 3 - 题目录入与知识点分析
- [x] 后端 API：题目 CRUD + DeepSeek 分析接口
- [x] 题目录入页面（图片上传 + LaTeX预览 + AI识别）
- [x] 知识点审核页面（下拉选章节 + 动态添加）
- [x] DeepSeek API 集成（知识点+权重+标签分析）
- [x] 图片上传 + AI 题目识别（v1.1.1）
- [x] KaTeX 数学公式实时预览（v1.1.1）
- [x] 知识点分级系统：主要/次要 + 权重（v1.1.0）
- [x] Tag 标签系统（v1.1.0）

## Phase 4 - 掌握度标记与统计
- [x] 后端 API：掌握度标记 + 统计聚合接口
- [x] 题目列表页（筛选 + 搜索）
- [x] 题目详情页 + 掌握度标记
- [x] 统计仪表盘（Chart.js 图表）
- [x] 薄弱知识点排序算法

## Phase 5 - 数据管理与代码审查
- [x] 后端 API：题库导入/导出（JSON 格式，含 role/weight/tags）
- [ ] **[neon-postgres]** 数据库分支备份策略
- [x] **[coderabbit]** 全项目代码审查（已完成多轮：v1.0.2, v1.1.1）
- [x] 根据审查结果修复问题（累计修复 15+ 个问题）

## Phase 6 - 优化与扩展（后期）
- [x] 图片上传 + AI 识别题目（v1.1.1）
- [x] 批量录入优化（v1.0.2）
- [x] DeepSeek API 调用缓存（v1.0.2）
- [ ] 复习推荐算法

---

## 进度记录
| 日期 | 完成内容 |
|-------------|---------|
| 2026-06-23 | 项目启动，完成需求讨论与架构设计 |
| 2026-06-23 | 引入插件体系：build-web-apps、neon-postgres、coderabbit |
| 2026-06-23 | v1.0.0 发布至 GitHub（Flask + SQLite + Bootstrap） |
| 2026-06-23 | v1.0.1 发布：搜索、编辑、知识点审核优化 |
| 2026-06-24 | CodeRabbit 审查完成，修复 IDE 配置泄露 |
| 2026-06-24 | v1.0.2 发布：CodeRabbit审查修复 + 批量录入 + API缓存 |
| 2026-06-24 | v1.1.0 发布：知识点分级/权重/tags系统 |
| 2026-06-24 | v1.1.1 发布：图片上传、AI题目识别、LaTeX预览、CodeRabbit修复 |
