# 项目管理看板图标实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 将已确认的 B 方案“蓝色工作台”图标接入窗口标题栏、Windows 任务栏和系统托盘，并生成可供后续安装器复用的多尺寸 Windows 图标。

**Architecture:** 新建 `icon.py` 负责用 Pillow 绘制确定性的 RGBA 图标和导出 `.ico`；`ui.py` 只调用图标工厂，不再直接维护图形细节。窗口使用 `ImageTk.PhotoImage`、Windows `iconbitmap` 和 `WM_SETICON`，主入口设置稳定的 AppUserModelID，托盘继续使用相同的 Pillow 图像。

**Tech Stack:** Python 3.11+, Tkinter/ImageTk, Pillow, pystray, pytest。

---

### Task 1: 图标工厂与导出

**Files:**
- Create: `src/project_manager/icon.py`
- Test: `tests/test_icon.py`

- [x] **Step 1:** 写失败测试，要求 `create_app_icon(64)` 返回 `RGBA`、尺寸为 `64x64`，且包含 B 方案的蓝色背景与浅色工作台面板；要求 `save_app_icon(path)` 生成可被 Pillow 读取的 `.ico`。
- [x] **Step 2:** 运行 `python -m pytest tests/test_icon.py -q`，确认模块尚不存在导致失败。
- [x] **Step 3:** 实现 `create_app_icon(size)`，绘制蓝色圆角底、浅色列表面板、三条列表线和三个底部状态节点；实现 `save_app_icon(path)`，写入 16、20、24、32、48、64、128、256 多尺寸。
- [x] **Step 4:** 运行图标 focused tests，确认图像模式、尺寸、关键像素和 ICO 多尺寸读取通过。

### Task 2: 窗口与托盘接入

**Files:**
- Modify: `src/project_manager/ui.py`
- Test: `tests/test_ui_state.py`

- [x] **Step 1:** 增加 Tk smoke assertion，应用初始化后存在非空的窗口图标引用，且托盘工厂调用同一图标函数。
- [x] **Step 2:** 在 `_build_widgets` 中用 `.ico` 调用 `root.iconbitmap(default=...)`，再用 `ImageTk.PhotoImage(create_app_icon(64))` 设置 `root.iconphoto(True, ...)` 并保留引用；在 `TrayController.start` 中调用同一工厂。
- [x] **Step 2a:** 在创建 Tk 根窗口前设置稳定的 `VibeManage.ProjectManager` AppUserModelID，避免 Windows 任务栏回退到 Python 默认图标。
- [x] **Step 2b:** 通过 `set_windows_window_icon` 对 Tk 窗口句柄发送大/小图标，覆盖 Windows 任务栏的可执行文件默认图标回退。
- [x] **Step 3:** 保持 `no_tray=True` 测试路径不创建托盘，避免影响现有 Tk 测试稳定性。
- [x] **Step 4:** 运行 focused Tk 测试，确认窗口初始化和页面切换仍通过。

### Task 3: 资产、文档与运行验证

**Files:**
- Create: `assets/project-manager-icon.ico`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-06-settings-ui-optimization.md`

- [x] **Step 1:** 用图标工厂生成项目内 `assets/project-manager-icon.ico`，作为后续安装器的稳定入口。
- [x] **Step 2:** 更新 README，说明窗口、托盘和安装器预留共用该图标。
- [x] **Step 3:** 运行完整 pytest、自检，并以隐藏控制台方式重启开发版应用。
- [x] **Step 4:** 检查窗口标题栏图标和托盘图标不再使用默认 Tk 图标；复制更新后的 Markdown 计划到 `D:\坚果云同步\ACO\codex outputs\06-文档\` 并刷新索引。
