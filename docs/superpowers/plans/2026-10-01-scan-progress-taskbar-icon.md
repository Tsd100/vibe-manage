# 扫描进度与任务栏图标清晰度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让扫描进度可见、减少重复文件遍历，并让任务栏使用清晰的小尺寸图标。

**Architecture:** 扫描器暴露可选进度回调并合并文件时间遍历；UI 通过 Tk `after` 转发进度。图标生成器提供简化的小尺寸帧，Windows 帮助函数选择 DPI 对应帧和顶层窗口句柄。

**Tech Stack:** Python 3.11、Tkinter、Pillow、ctypes、pytest。

---

### Task 1: 扫描器进度与一次文件遍历

**Files:** `src/project_manager/scanner.py`、`tests/test_scanner.py`

- [ ] 添加两个仓库的回调测试，断言收到 `(0, 2, ...)`、`(1, 2, ...)`、`(2, 2, ...)`。
- [ ] 添加文件遍历计数测试，断言扫描单仓库时项目发现一次、文件时间计算一次。
- [ ] 运行 `python -m pytest tests/test_scanner.py -q`，确认新测试因缺少功能失败。
- [ ] 实现可选 `progress` 回调与单次遍历的文件时间辅助函数，保持既有返回字段。
- [ ] 重跑扫描器测试直至通过。

### Task 2: UI 进度显示

**Files:** `src/project_manager/ui.py`、`tests/test_ui_state.py`

- [ ] 添加测试验证进度消息格式与扫描完成后状态恢复。
- [ ] 运行对应测试，确认失败。
- [ ] 在后台扫描线程回调中通过 `root.after` 更新 `status_var`，不跨线程直接改 Tk 控件。
- [ ] 重跑 UI 测试。

### Task 3: 高 DPI 图标

**Files:** `src/project_manager/icon.py`、`src/project_manager/windows.py`、`assets/project-manager-icon.ico`、`tests/test_icon.py`、`tests/test_windows_icon.py`

- [ ] 添加测试验证小尺寸帧可辨识的粗笔画和 DPI 尺寸选择。
- [ ] 运行对应测试，确认失败。
- [ ] 绘制简化小尺寸图标，原生窗口图标加载匹配尺寸并设置顶层句柄。
- [ ] 重新生成 ICO，重跑对应测试。

### Task 4: 集成验证与交付

- [ ] 运行 `python -m pytest -q` 和 `git diff --check`。
- [ ] 检查 Git 暂存内容不含数据或密钥，提交并推送至既有 GitHub remote。
- [ ] 重启正式应用，核对进程、扫描结果与图标显示；如无法直接读取任务栏视觉，明确说明验证边界。
