# Grad Question Bank - 考研智能题库系统

## 项目定位
题库管理 + 知识点掌握度分析系统。核心流程：
录入题目 → DeepSeek分析知识点 → 用户审核/调整 → 标记掌握情况 → 统计分析

## 技术栈（已更新）
- 前端：React + Vite（由 **build-web-apps** 插件负责设计与实现）
- 后端：Python + Flask（纯 JSON API，不再渲染模板）
- 数据库：Neon Postgres（由 **neon-postgres** 插件管理，支持分支备份）
- 图表：Recharts 或 Chart.js
- AI：DeepSeek API（知识点分析）
- 代码审查：CodeRabbit（由 **coderabbit** 插件执行）

## 插件依赖
| 插件 | 用途 | 触发时机 |
|------|------|---------|
| build-web-apps | 前端 UI 设计与实现 | Phase 1 前端搭建、UI 重构 |
| neon-postgres | 数据库创建与管理 | Phase 1 数据库初始化 |
| coderabbit | 代码质量审查 | Phase 5 代码审查 |

## 数据设计
- 三级结构：学科 → 章节 → 知识点
- 掌握度三级：已掌握 / 模糊 / 完全不会
- 题目只存题干（含选项文字）+ 结果答案
- 预置政治、计算机408的基础知识点骨架，用户可自行扩展

---

## Phase 1 - 项目骨架与基础设施
- [ ] 初始化前后端分离项目结构
- [ ] 后端：Flask API 项目（纯 JSON 接口，无模板渲染）
- [ ] 前端：React + Vite 项目初始化
- [ ] **[neon-postgres]** 创建 Neon Postgres 数据库，建表
- [ ] 预置种子数据（政治 + 计算机408）
- [ ] **[build-web-apps]** 设计并实现前端整体布局与导航

## Phase 2 - 学科知识体系管理
- [ ] 后端 API：学科/章节/知识点 CRUD
- [ ] **[build-web-apps]** 学科管理页面（列表 + 增删）
- [ ] **[build-web-apps]** 章节管理页面
- [ ] **[build-web-apps]** 知识点管理页面

## Phase 3 - 题目录入与知识点分析
- [ ] 后端 API：题目 CRUD + DeepSeek 分析接口
- [ ] **[build-web-apps]** 题目录入页面
- [ ] **[build-web-apps]** 知识点审核页面（AI 分析结果 + 用户修改）
- [ ] 前后端联调

## Phase 4 - 掌握度标记与统计
- [ ] 后端 API：掌握度标记 + 统计聚合接口
- [ ] **[build-web-apps]** 题目列表页（筛选 + 搜索）
- [ ] **[build-web-apps]** 题目详情页 + 掌握度标记
- [ ] **[build-web-apps]** 统计仪表盘（图表可视化）
- [ ] 薄弱知识点排序算法

## Phase 5 - 数据管理与代码审查
- [ ] 后端 API：题库导入/导出（JSON 格式）
- [ ] **[build-web-apps]** 导入/导出页面
- [ ] **[neon-postgres]** 数据库分支备份策略
- [ ] **[coderabbit]** 全项目代码审查
- [ ] 根据审查结果修复问题

## Phase 6 - 优化与扩展（后期）
- [ ] OCR 图片识别提取题目
- [ ] 批量录入优化
- [ ] DeepSeek API 调用缓存（避免重复分析相同题目）
- [ ] 复习推荐算法

---

## 进度记录
| 日期 | 完成内容 |
|------|---------|
| 2026-06-23 | 项目启动，完成需求讨论与架构设计 |
| 2026-06-23 | 引入插件体系：build-web-apps（前端）、neon-postgres（数据库）、coderabbit（审查）|
