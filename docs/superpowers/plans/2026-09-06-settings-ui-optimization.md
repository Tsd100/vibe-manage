# 设置页与工作台 UI 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 在保留 Tkinter、扫描、托盘和 D 盘数据边界的前提下，吸收 skillmanage 的分组设置、统一控件、主题缩放和诊断反馈优点，完善本项目的桌面工作台。

**Architecture:** 继续使用现有 `ProjectManagerApp` 和 `JsonStore`，把新增设置收敛到 `UiSettings` 的可迁移字段；设置页按项目来源、扫描行为、显示与窗口、数据与诊断分组，每个分组使用卡片和说明行。所有变更仍保存到 `D:\Program Files (x86)\ProjectManagerData\settings.json`，不改变项目仓库只读扫描边界。

**Tech Stack:** Python 3.11+, Tkinter/ttk, pytest, pystray, Pillow。

---

### Task 1: 扩展设置模型并固定行为

**Files:**
- Modify: `src/project_manager/settings.py`
- Test: `tests/test_settings.py`

- [x] **Step 1: Write failing tests** for `default_page`, `compact_layout`, `theme_mode`, and `settings_version` defaults and invalid-value fallback.
- [x] **Step 2: Run `python -m pytest tests/test_settings.py -q`** and verify the new fields are missing or rejected.
- [x] **Step 3: Add typed fields and normalization** while preserving all existing settings and column-width validation.
- [x] **Step 4: Run the focused settings tests** and verify all pass.

### Task 2: Rebuild the settings page into grouped cards

**Files:**
- Modify: `src/project_manager/ui.py`
- Test: `tests/test_ui_state.py`

- [x] **Step 1: Write a Tk smoke assertion** that the settings page exposes the five groups `项目来源`, `扫描行为`, `显示与布局`, `窗口与托盘`, and `数据与诊断`.
- [x] **Step 2: Run the focused UI test** and verify the group widgets do not exist yet.
- [x] **Step 3: Replace the single settings card** with grouped cards using the existing theme tokens, label-plus-description rows, folder chooser, segmented controls, and status feedback.
- [x] **Step 4: Wire root-directory, depth, auto-scan, tray, scale, default-page, and compact-layout controls to the expanded settings model.
- [x] **Step 5: Run the focused Tk test** with `no_tray=True` and verify page switching still hides other pages.

### Task 3: Add data and diagnostic actions

**Files:**
- Modify: `src/project_manager/ui.py`
- Modify: `src/project_manager/storage.py` only if export helpers need a narrow reusable function
- Test: `tests/test_ui_state.py`, `tests/test_storage.py` if applicable

- [x] **Step 1: Write failing tests** for a diagnostics summary that reports data directory, root count, project count, and last scan time without exposing secrets.
- [x] **Step 2: Implement reset-to-defaults, open-data-directory, and copy/export-diagnostics actions** using Windows-safe `os.startfile`/clipboard fallbacks and parented message boxes.
- [x] **Step 3: Keep diagnostics read-only** and ensure no project files under configured roots are modified.
- [x] **Step 4: Run focused storage/UI tests** and verify the diagnostics summary and settings actions in the Tk smoke test.

### Task 4: Visual and runtime verification

**Files:**
- Modify: `README.md` to document the new settings groups
- Modify: `docs/superpowers/plans/2026-09-06-project-manager-desktop-pages.md` with the completed follow-up

- [x] **Step 1:** Run `python -m pytest -q` and require the full suite to pass.
- [x] **Step 2:** Run a Tk smoke test at `1280x780` and a 4K-scale configuration, covering settings, overview, timeline, and scan record.
- [x] **Step 3:** Restart the hidden-console development app with the D-drive data directory and verify the process title is `项目管理看板`.
- [x] **Step 4:** Copy the updated Markdown plan to `D:\坚果云同步\ACO\codex outputs\06-文档\` and refresh the output index.

### Task 5: 项目总览排序与布局记忆

**Files:**
- Modify: `src/project_manager/settings.py`
- Modify: `src/project_manager/ui.py`
- Test: `tests/test_settings.py`, `tests/test_ui_state.py`

- [x] **Step 1:** 先写排序模式和设置持久化测试，覆盖最近修改、创建时间、名称、关注优先以及非法值回退。
- [x] **Step 2:** 增加 `project_sort` 设置字段和纯排序函数，保持关注信号优先、同类按最近活动排序。
- [x] **Step 3:** 在项目总览筛选栏增加排序下拉框，在设置页显示与布局分组同步该选项，并保存到 D 盘 `settings.json`。
- [x] **Step 4:** 将扫描记录表格列纳入列宽持久化和恢复默认操作。
- [x] **Step 5:** 运行排序、设置和 Tk smoke tests。

### Task 6: 扫描历史可追溯

**Files:**
- Create: `src/project_manager/scan_history.py`
- Modify: `src/project_manager/ui.py`
- Modify: `README.md`
- Test: `tests/test_scan_history.py`, `tests/test_ui_state.py`

- [x] **Step 1:** 先写扫描记录构造、清洗、最多 50 条倒序保存测试。
- [x] **Step 2:** 新增 `inventory/scan-history.json` 存储边界，记录开始/完成时间、耗时、状态、项目数、根目录数和错误信息。
- [x] **Step 3:** 扫描记录页增加最近扫描 Treeview 和选中记录摘要；成功与失败扫描都写入历史。
- [x] **Step 4:** 更新 README 的数据目录说明，并运行完整测试确认不影响原有扫描流程。

### Task 7: 统一时间显示格式

**Files:**
- Modify: `src/project_manager/ui.py`
- Modify: `README.md`
- Test: `tests/test_ui_state.py`

- [x] **Step 1:** 先写 ISO 时间显示回归测试，覆盖时区、微秒、日期-only 和无效值。
- [x] **Step 2:** 增加纯显示格式化函数，将界面时间统一按北京时间（UTC+8）渲染为 `YYYY-MM-DD HH:MM:SS`，不改写注册表、时间线和扫描历史原始数据。
- [x] **Step 3:** 接入项目详情、总览表格、时间线、扫描记录和诊断摘要显示位置。
- [x] **Step 4:** 运行完整测试并重启开发版应用验证窗口正常响应。

### Task 8: 项目总览近期修改时间

**Files:**
- Modify: `src/project_manager/ui.py`
- Modify: `README.md`
- Test: `tests/test_ui_state.py`

- [x] **Step 1:** 先写固定北京时间基准下的“今天 / 昨天 / 更早”格式化测试。
- [x] **Step 2:** 增加近期时间格式化函数，按北京时间计算日期差；无效或只有日期的值继续使用完整显示格式。
- [x] **Step 3:** 仅将项目总览“最后修改”列接入相对日期显示，详情和时间线保留完整日期时间。
- [x] **Step 4:** 运行完整测试并重启开发版应用。

### Task 9: 排除参考仓库的进度统计

**Files:**
- Modify: `src/project_manager/ui.py`
- Modify: `README.md`
- Test: `tests/test_ui_state.py`

- [x] **Step 1:** 先写参考仓库识别和管理视图过滤测试，覆盖 `scope=参考仓库` 与 `_references/` 路径。
- [x] **Step 2:** 增加纯过滤函数，将参考仓库保留在注册表和扫描数量中，但排除项目总览、统计卡和全局时间线。
- [x] **Step 3:** 更新 README 说明边界，运行完整测试并重启开发版应用。
