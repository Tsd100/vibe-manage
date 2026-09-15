# Project Manager A 方案 UI 美化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Tkinter 项目管理看板改造成浅色、专业的「北极星工作台」，提升长期查看项目用途、状态和时间线时的可读性。

**Architecture:** 保留现有扫描、JSON 存储、人工覆盖、时间线和托盘控制器，只重做 `ProjectManagerApp._build_widgets` 及其展示辅助方法。界面采用固定侧栏 + 顶部概览卡 + 中央项目列表 + 右侧详情面板，继续使用 Tkinter/ttk，不引入新的运行时依赖。

**Tech Stack:** Python 3.11+, Tkinter/ttk, 现有 `ProjectManagerApp`, pytest。

---

### Task 1: 为 A 方案增加可测试的展示计算辅助函数

**Files:**
- Modify: `src/project_manager/ui.py`
- Test: `tests/test_ui_state.py`

- [ ] **Step 1: 写失败测试**

新增 `project_summary_counts(projects)`，返回 `total`、`active`、`attention` 三个整数；新增 `status_tone(project)`，将“进行中/开发中”归为 `active`，将“暂停/阻塞/需关注”归为 `attention`，其他归为 `neutral`。

- [ ] **Step 2: 运行测试确认失败**

运行：`$env:PYTHONPATH='src'; python -m pytest tests/test_ui_state.py -q`

预期：因函数尚未存在而失败。

- [ ] **Step 3: 实现最小辅助函数**

函数只读取项目映射中的 `manual_status`，缺失时使用“未确认”；不修改输入列表，不引入 UI 依赖。

- [ ] **Step 4: 运行测试确认通过**

运行同一命令，预期全部通过。

### Task 2: 建立浅色工作台主题和整体布局

**Files:**
- Modify: `src/project_manager/ui.py`

- [ ] **Step 1: 配置主题常量和 ttk 样式**

加入深蓝侧栏、浅灰画布、白色卡片、蓝色主操作、绿色成功、橙色关注色；设置 `Treeview` 行高、表头、选中态和滚动条样式。字体优先使用 Segoe UI，中文由系统回退。

- [ ] **Step 2: 将 `_build_widgets` 改为四层布局**

根容器包含：左侧 176px 导航栏、右侧工作区；工作区上方为标题/路径/刷新/编辑操作栏，中部为三个概览统计卡，下方为项目列表与详情时间线的水平分栏。保留窗口最小尺寸和现有按钮命令绑定。

- [ ] **Step 3: 增加统计卡刷新逻辑**

新增 `self.total_var`、`self.active_var`、`self.attention_var`，在 `_render_projects` 中依据当前项目列表更新，筛选结果只影响列表计数，不影响总览统计。

### Task 3: 美化项目列表和详情时间线

**Files:**
- Modify: `src/project_manager/ui.py`

- [ ] **Step 1: 保持 Treeview 数据结构，增加状态标签色**

继续使用项目 id 作为 Treeview iid，保留项目、状态、阶段、最后修改四列；根据 `status_tone` 添加 `active/attention/neutral` 标签，避免修改筛选和选择逻辑。

- [ ] **Step 2: 将详情 Text 改为带标签的摘要面板**

使用标题、字段标签、路径、时间线事件和验证结果的颜色标签；保留现有所有字段和事件来源，不改变 `project_events` 输出。

- [ ] **Step 3: 优化人工字段对话框**

维持原有字段和保存逻辑，只增加宽度、间距、说明文字和主题按钮样式，确保人工覆盖仍写入 `D:\Program Files (x86)\ProjectManagerData\overrides`。

### Task 4: 验证窗口、托盘和刷新回归

**Files:**
- Modify: `tests/test_ui_state.py` only if helper assertions need completion

- [ ] **Step 1: 运行完整自动化测试**

运行：`$env:PYTHONPATH='src'; python -m pytest -q`

- [ ] **Step 2: 运行 Tk 无托盘 smoke test**

以 `--no-tray` 创建 Tk 根窗口，构造 `ProjectManagerApp`，确认窗口可创建、统计卡存在、调用 `hide_to_tray` 后窗口 withdrawn，再销毁窗口。

- [ ] **Step 3: 重启开发版应用供用户验收**

使用默认参数启动：`$env:PYTHONPATH='src'; python -m project_manager --repo-root 'D:\Github' --data-dir 'D:\Program Files (x86)\ProjectManagerData'`。不执行安装、打包或全局 Git 配置修改。
