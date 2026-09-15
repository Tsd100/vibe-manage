# Project Manager 筛选与关注信号实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 为 A 方案首页补上状态、阶段和自动关注信号筛选，让 41 个项目可以快速缩小到需要处理的集合。

**Architecture:** 筛选规则保持纯函数，输入项目映射和筛选条件，输出项目列表；Tkinter 只负责读取控件值并调用规则。自动关注信号只作为提醒，不改变人工状态，也不写入业务仓库。

**Tech Stack:** Python 3.11+, Tkinter/ttk, pytest。

---

### Task 1: 增加纯函数筛选规则

**Files:**
- Modify: `src/project_manager/ui.py`
- Modify: `tests/test_ui_state.py`

- [ ] **Step 1: 写失败测试**

覆盖状态筛选、阶段筛选、组合筛选和关注信号：关注信号包括未提交文件、用途待补充、验证状态为环境阻塞/失败，以及人工状态为阻塞/暂停。

- [ ] **Step 2: 运行 `PYTHONPATH=src python -m pytest tests/test_ui_state.py -q`，确认新函数尚不存在。**

- [ ] **Step 3: 实现 `filter_projects_advanced` 和 `has_attention_signal`，不改变原有 `filter_projects` 的搜索行为。**

- [ ] **Step 4: 运行 focused tests，确认筛选规则通过。**

### Task 2: 将筛选控件接入 A 方案工作台

**Files:**
- Modify: `src/project_manager/ui.py`

- [ ] **Step 1:** 在项目列表标题下增加状态下拉、阶段下拉和“只看需关注”复选框。

- [ ] **Step 2:** 将控件值传给 `_render_projects`，列表计数、统计卡和 Treeview 状态标签保持一致。

- [ ] **Step 3:** 在 Treeview 项目名称前不改变 id，关注项目增加橙色标记；详情仍由同一选择事件驱动。

### Task 3: 回归验证与开发版重启

**Files:**
- Modify: `tests/test_ui_state.py` only when assertions need completion

- [ ] **Step 1:** 运行完整测试：`$env:PYTHONPATH='src'; python -m pytest -q`。

- [ ] **Step 2:** 运行 Tk 无托盘 smoke test，确认控件存在、筛选后可以选择项目、关闭窗口仍为 withdrawn。

- [ ] **Step 3:** 重启开发版，保持项目根目录 `D:\Github` 和数据目录 `D:\Program Files (x86)\ProjectManagerData`。
