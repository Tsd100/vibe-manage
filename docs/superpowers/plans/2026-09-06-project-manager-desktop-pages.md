# Project Manager 桌面多页面实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 将浏览器演示中已确认的项目总览、时间线、扫描记录导航同步到 Tkinter 桌面应用。

**Architecture:** 保留现有扫描、注册表、人工覆盖、时间线和托盘逻辑；在同一窗口中使用页面容器切换，项目总览继续复用现有 Treeview，时间线从 `project_events` 生成事件列表，并纳入创建时间、最后修改时间、提交、工作树和验证证据，扫描记录展示当前数据目录和最近扫描状态。设置页持久化扫描深度、托盘行为、启动扫描和界面缩放配置。

**Tech Stack:** Python 3.11+, Tkinter/ttk, pytest。

---

### Task 1: 增加页面状态测试

**Files:**
- Modify: `tests/test_ui_state.py`
- Modify: `src/project_manager/ui.py`

- [ ] **Step 1:** 为页面名称规范化增加纯函数测试，覆盖项目总览、时间线、扫描记录和未知页面回退。
- [ ] **Step 2:** 运行 focused test 确认函数不存在。
- [ ] **Step 3:** 实现 `normalize_page_name`，不依赖 Tkinter。

### Task 2: 将桌面窗口改为页面导航

**Files:**
- Modify: `src/project_manager/ui.py`

- [ ] **Step 1:** 将侧栏静态标签改为可点击导航按钮，增加标题和操作区的页面状态绑定。
- [ ] **Step 2:** 将现有总览控件放入总览页面容器，新增时间线、扫描记录和设置占位页面。
- [ ] **Step 3:** 实现时间线项目/事件类型筛选和事件详情；扫描记录显示 D 盘数据目录、仓库数量和最近扫描状态。

### Task 3: 回归验证

- [ ] **Step 1:** 运行完整 pytest。
- [ ] **Step 2:** 运行 Tk 无托盘 smoke test，切换三个页面、检查标题，再验证关闭到托盘。
- [ ] **Step 3:** 使用隐藏控制台方式重启开发版应用，避免再次弹出终端窗口。

### Follow-up fixes

- 页面切换前统一隐藏所有页面容器，避免时间线、扫描记录和设置页叠加。
- 设置保存到数据目录的 `settings.json`，扫描器读取最大扫描深度。
- Windows 启动前启用每显示器 DPI 感知，界面缩放相对系统 Tk 缩放计算。
- 项目根目录改为可编辑的多目录列表，设置持久化到 `repo_roots`；扫描跨目录合并并按绝对路径去重，保留第一个根目录的既有项目 ID 以兼容人工覆盖。
- 项目详情页的路径统一展开为 Windows 绝对路径，兼容新注册表的 `root` 字段和旧注册表的相对路径。
- 项目总览和时间线的 Treeview 列支持拖拽调整，宽度自动保存到 `settings.json` 的 `column_widths` 并在下次启动恢复，同时提供横向滚动条。
- 项目总览按已确认的 A 方案重做下半区：状态/阶段筛选、自动选中项目、结构化详情字段、状态徽章和最近时间线卡片。
- 编辑人工字段改为应用内居中的模态窗口：状态、阶段、优先级使用预设下拉选项，创建时间使用内置月历及时分秒选择器，并保留人工覆盖数据结构。
- 设置页参考 skillmanage 重构为项目来源、扫描行为、显示与布局、窗口与托盘、数据与诊断五组；新增默认页面、紧凑布局、主题模式、诊断摘要和恢复列宽入口。
- 项目总览新增最近修改、创建时间、名称、关注优先四种排序；排序选择写入 `settings.json`，扫描记录表格列宽同样支持持久化。
- 扫描记录页新增最近 50 次扫描历史，保存完成时间、耗时、结果、项目数量、根目录数量和失败信息到 `inventory/scan-history.json`。
