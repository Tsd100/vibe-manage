# GitHub 开源属性实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每个项目加入基于 Git remote 的 GitHub 开源状态、人工覆盖、详情展示、搜索和时间线记录。

**Architecture:** 扫描器只负责读取 remote 并生成自动判断字段；已有 overrides 负责保存人工选择，合并时人工值优先。时间线模块继续生成 Git/文件系统事件，同时持久化人工开源状态事件，UI 通过统一的有效值字段展示，不增加项目列表列。

**Tech Stack:** Python 3.11、Tkinter/ttk、JSON 文件存储、pytest、Git CLI。

---

## 文件结构与职责

- Modify: `src/project_manager/scanner.py` — 读取 Git remote、解析 GitHub 地址、生成自动状态。
- Modify: `src/project_manager/models.py` — 扩展 `ProjectRecord` 字段，兼容旧注册表。
- Modify: `src/project_manager/storage.py` — 提供人工覆盖值的归一化和有效值合并规则。
- Modify: `src/project_manager/timeline.py` — 生成开源状态事件，保留已有事件排序。
- Modify: `src/project_manager/ui.py` — 详情字段、编辑下拉框、搜索字段和人工事件持久化。
- Modify: `tests/test_scanner.py` — remote 解析、扫描记录和失败降级测试。
- Modify: `tests/test_storage.py` — 自动/人工值优先级和清除覆盖测试。
- Modify: `tests/test_timeline.py` — 开源状态事件与人工事件排序测试。
- Modify: `tests/test_ui_state.py` — 详情、搜索、编辑字段测试及现有 Tk 设置测试断言。
- Modify: `README.md` — 说明自动判断范围、人工覆盖和不上传项目内容的行为。

### Task 1: Git remote 自动判断

**Files:**
- Modify: `src/project_manager/scanner.py`
- Modify: `src/project_manager/models.py`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: 写失败测试，覆盖三种 remote 格式和失败降级**

在 `tests/test_scanner.py` 增加：

```python
def test_parse_github_remote_supports_https_ssh_and_scp_like():
    from project_manager.scanner import parse_github_remote

    assert parse_github_remote("https://github.com/acme/demo.git") == "https://github.com/acme/demo.git"
    assert parse_github_remote("ssh://git@github.com/acme/demo.git") == "ssh://git@github.com/acme/demo.git"
    assert parse_github_remote("git@github.com:acme/demo.git") == "git@github.com:acme/demo.git"
    assert parse_github_remote("https://gitlab.com/acme/demo.git") is None


def test_git_metadata_marks_remote_failure_as_unconfirmed(monkeypatch, tmp_path):
    from project_manager import scanner

    def failed_git(_repo, *args, **kwargs):
        if args[:2] == ("remote", "-v"):
            raise scanner.GitCommandError("remote unavailable")
        return ""

    monkeypatch.setattr(scanner, "_git", failed_git)
    metadata = scanner.git_metadata(tmp_path)

    assert metadata["github_open_source"] == "未确认"
    assert metadata["github_open_source_source"] == "auto_git_remote"
    assert metadata["github_remote_url"] == ""
```

- [ ] **Step 2: 运行测试确认按预期失败**

运行：`python -m pytest tests/test_scanner.py -k "github_remote or remote_failure" -v`

预期：失败，提示 `parse_github_remote` 或 `GitCommandError` 尚未定义。

- [ ] **Step 3: 实现最小 remote 解析和命令结果区分**

在 `scanner.py` 中加入：

```python
class GitCommandError(RuntimeError):
    pass


def parse_github_remote(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    host = ""
    if text.startswith("git@") and ":" in text:
        host = text[4:].split(":", 1)[0].lower()
    else:
        from urllib.parse import urlparse
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower()
    return text if host in {"github.com", "www.github.com"} else None
```

将 `_git` 改为命令失败/超时抛出 `GitCommandError`，成功时返回 stdout；`git_metadata` 读取 `git remote -v`，按 remote 名去重，选第一个 GitHub URL，并返回：

```python
"github_open_source": "是" | "否" | "未确认",
"github_open_source_source": "auto_git_remote",
"github_remote_url": str,
```

没有 GitHub remote 且命令成功为 `否`；失败为 `未确认`。把上述字段加入 `scan_projects` 记录，并在 `ProjectRecord`/`from_mapping` 中给旧数据默认值。

- [ ] **Step 4: 运行扫描器测试确认通过**

运行：`python -m pytest tests/test_scanner.py -v`

预期：该文件全部通过，既有无提交仓库测试仍通过。

- [ ] **Step 5: 提交扫描器与模型变更**

```powershell
git add tests/test_scanner.py src/project_manager/scanner.py src/project_manager/models.py
git commit -m "feat: detect GitHub remotes during scans"
```

### Task 2: 人工覆盖与时间线事件

**Files:**
- Modify: `src/project_manager/storage.py`
- Modify: `src/project_manager/timeline.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_timeline.py`

- [ ] **Step 1: 写失败测试，明确人工优先级和人工事件**

在 `tests/test_storage.py` 增加：

```python
def test_merge_manual_github_value_overrides_auto_and_empty_restores_auto():
    auto = {
        "id": "repo:demo",
        "github_open_source": "是",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "https://github.com/acme/demo",
    }
    assert merge_manual_overrides(auto, {"repo:demo": {"manual_github_open_source": "否"}})["github_open_source"] == "否"
    restored = merge_manual_overrides(auto, {"repo:demo": {"manual_github_open_source": ""}})
    assert restored["github_open_source"] == "是"
    assert restored["github_open_source_source"] == "auto_git_remote"
```

在 `tests/test_timeline.py` 增加：

```python
def test_project_events_include_github_status_and_manual_history():
    events = project_events({
        "github_open_source": "是",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "https://github.com/acme/demo",
        "github_open_source_history": [{
            "at": "2026-09-06T12:00:00+08:00",
            "value": "否",
            "source": "manual",
        }],
    })
    assert any(event.event_type == "github_open_source" and event.source == "auto_git_remote" for event in events)
    assert any(event.event_type == "github_open_source" and event.source == "manual" for event in events)
```

- [ ] **Step 2: 运行测试确认失败**

运行：`python -m pytest tests/test_storage.py tests/test_timeline.py -k "github" -v`

预期：失败，因为合并函数尚未计算有效值，时间线尚未读取状态历史。

- [ ] **Step 3: 实现合并规则和事件生成**

在 `storage.py` 的 `merge_manual_overrides` 中读取 `manual_github_open_source`：空值删除/忽略覆盖并保留自动字段，`是/否` 则写入有效 `github_open_source` 并将来源改为 `manual`。保留原 overrides 中其他键。

在 `timeline.py` 中添加 `github_open_source` 事件：当前字段存在时生成一条摘要，包含状态和 remote（有值时）；再读取可选的 `github_open_source_history` 列表，逐条生成历史事件。所有事件继续通过 `build_timeline` 排序。

- [ ] **Step 4: 运行存储和时间线测试确认通过**

运行：`python -m pytest tests/test_storage.py tests/test_timeline.py -v`

预期：两个文件全部通过，旧事件排序断言不变。

- [ ] **Step 5: 提交数据流与时间线变更**

```powershell
git add tests/test_storage.py tests/test_timeline.py src/project_manager/storage.py src/project_manager/timeline.py
git commit -m "feat: persist GitHub status overrides in timeline"
```

### Task 3: 总览详情、编辑窗口和搜索

**Files:**
- Modify: `src/project_manager/ui.py`
- Test: `tests/test_ui_state.py`

- [ ] **Step 1: 写失败的纯函数测试**

更新 `test_project_detail_fields_match_overview_detail_sections` 的期望，加入：

```python
("GitHub 开源", "是（自动判断）\nhttps://github.com/acme/demo"),
```

并增加：

```python
def test_filter_projects_matches_github_status_and_remote():
    projects = [{
        "name": "demo",
        "purpose": "用途",
        "github_open_source": "是",
        "github_remote_url": "https://github.com/acme/demo",
    }, {"name": "local", "github_open_source": "否"}]
    assert [item["name"] for item in filter_projects(projects, "github.com")] == ["demo"]
    assert [item["name"] for item in filter_projects(projects, "开源")] == ["demo"]


def test_manual_override_includes_github_field():
    result = build_manual_override({"manual_github_open_source": "否"})
    assert result["manual_github_open_source"] == "否"
```

- [ ] **Step 2: 运行 UI 纯函数测试确认失败**

运行：`python -m pytest tests/test_ui_state.py -k "detail_fields or filter_projects_matches_github or manual_override_includes_github" -v`

预期：失败，因为详情字段、搜索字段和可编辑字段尚未包含 GitHub 属性。

- [ ] **Step 3: 实现 UI 最小改动**

在 `ui.py` 中：

1. 将 `manual_github_open_source` 加入 `EDITABLE_FIELDS`，定义 `GITHUB_OPEN_SOURCE_OPTIONS = ("未确认", "是", "否")`。
2. `project_detail_fields` 增加“GitHub 开源”值；自动值标注“（自动判断）”，人工值标注“（手动）”，有 remote 时换行显示地址。
3. `filter_projects` 的搜索文本加入 `github_open_source`、`github_remote_url` 和来源字段。
4. `_render_detail_panel` 在“状态”旁新增 GitHub 字段，不增加项目列表列。
5. 编辑窗口 labels 增加“GitHub 开源”，使用只读 `ttk.Combobox`。显示当前有效值；保存时把选择 `未确认` 转为 `manual_github_open_source=""`，`是/否` 原样保存。
6. 保存覆盖前读取已有项目时间线，比较旧的人工值与新值，仅在变化时追加 `{at, value, source:"manual"}` 到 `github_open_source_history`；随后保存 registry、刷新详情和时间线。

- [ ] **Step 4: 运行 UI 测试确认通过**

先关闭正在运行的项目管理程序，再运行：`python -m pytest tests/test_ui_state.py -v`

预期：UI 纯函数和现有 Tk 测试全部通过，设置页、托盘图标及页面切换断言不回归。

- [ ] **Step 5: 提交 UI 变更**

```powershell
git add tests/test_ui_state.py src/project_manager/ui.py
git commit -m "feat: show and edit GitHub open-source status"
```

### Task 4: 文档、回归验证与发布

**Files:**
- Modify: `README.md`
- Test: `tests/test_scanner.py`, `tests/test_storage.py`, `tests/test_timeline.py`, `tests/test_ui_state.py`

- [ ] **Step 1: 更新 README 的功能和隐私说明**

在功能列表加入“根据 Git remote 自动判断 GitHub 开源状态，并支持人工覆盖”；在数据说明中明确只读取本地 Git remote，不调用 GitHub API，不上传项目源代码或扫描快照。

- [ ] **Step 2: 运行完整测试套件**

运行：`python -m pytest -q`

预期：全部测试通过，输出无失败或错误。

- [ ] **Step 3: 做一次真实本地扫描验证**

运行项目自检/扫描入口，确认至少一个连接 GitHub 的仓库显示 `是` 和 remote 地址；创建一个无 GitHub remote 的临时仓库确认显示 `否`；无法读取 Git 的场景显示 `未确认`。不修改用户项目内容。

- [ ] **Step 4: 检查差异和敏感数据**

运行：`git diff --check`、`git status --short`，确认只包含源代码、测试、README 和规格/计划文档；确认没有 `inventory/projects-registry.json`、密钥或个人项目快照进入提交。

- [ ] **Step 5: 提交 README 和最终变更**

```powershell
git add README.md
git commit -m "docs: document GitHub open-source status"
```

- [ ] **Step 6: 推送到 GitHub 并验证远端**

```powershell
git push origin main
git log -1 --oneline
gh repo view Tsd100/vibe-manage --json isPrivate,defaultBranchRef,url
```

预期：推送成功，仓库仍为公开，默认分支为 `main`。随后重新启动本地应用，确认浏览器页面可访问且详情面板能看到新字段。
