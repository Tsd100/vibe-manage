# Project Management Desktop MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Build a runnable Windows desktop MVP for the project-management dashboard with A1 detail timelines, D-drive persistence, manual refresh, and tray-on-close behavior; defer installer packaging.

**Architecture:** A small Python application separates configuration, JSON storage, read-only repository scanning, timeline derivation, and the Tkinter/pystray shell. Business repositories under `D:\Github` are never edited. Runtime data defaults to `D:\Program Files (x86)\ProjectManagerData` and can be overridden only through an explicit CLI flag or environment variable for testing.

**Tech Stack:** Python 3.11+, Tkinter, pystray, Pillow, stdlib `subprocess`/`json`/`pathlib`, pytest.

**Execution status (2026-09-05):** Tasks 1–7 completed. The refresh-error path was smoke-tested; installer packaging remains intentionally deferred.

---

### Task 1: Create testable package boundaries and configuration

**Files:**
- Create: `pyproject.toml`
- Create: `src/project_manager/__init__.py`
- Create: `src/project_manager/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for D-drive defaults and explicit overrides**

```python
from pathlib import Path

from project_manager.config import AppConfig, DataDirectoryError


def test_defaults_point_to_d_drive():
    config = AppConfig.from_environment({})
    assert config.repo_root == Path(r"D:\Github")
    assert config.data_dir == Path(r"D:\Program Files (x86)\ProjectManagerData")


def test_data_directory_is_created_and_writable(tmp_path):
    config = AppConfig(repo_root=tmp_path, data_dir=tmp_path / "data")
    config.ensure_data_dirs()
    assert (tmp_path / "data" / "inventory").is_dir()


def test_permission_error_is_explicit(monkeypatch, tmp_path):
    config = AppConfig(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")))
    try:
        config.ensure_data_dirs()
    except DataDirectoryError as exc:
        assert "ProjectManagerData" in str(exc) or "data" in str(exc)
    else:
        raise AssertionError("expected DataDirectoryError")
```

- [ ] **Step 2: Run `python -m pytest tests/test_config.py -q` and confirm it fails because the package/config do not exist.**

- [ ] **Step 3: Implement `AppConfig`**

```python
DEFAULT_REPO_ROOT = Path(r"D:\Github")
DEFAULT_DATA_DIR = Path(r"D:\Program Files (x86)\ProjectManagerData")


@dataclass(frozen=True)
class AppConfig:
    repo_root: Path = DEFAULT_REPO_ROOT
    data_dir: Path = DEFAULT_DATA_DIR

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "AppConfig":
        env = os.environ if environ is None else environ
        return cls(Path(env.get("PROJECT_MANAGER_REPO_ROOT", DEFAULT_REPO_ROOT)),
                   Path(env.get("PROJECT_MANAGER_DATA_DIR", DEFAULT_DATA_DIR)))

    def ensure_data_dirs(self) -> None:
        try:
            for name in ("inventory", "overrides", "timeline", "logs"):
                (self.data_dir / name).mkdir(parents=True, exist_ok=True)
            probe = self.data_dir / "logs" / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise DataDirectoryError(f"无法写入数据目录：{self.data_dir}: {exc}") from exc
```

- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 2: Add JSON storage and manual overrides

**Files:**
- Create: `src/project_manager/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests for atomic JSON save/load and override preservation.**

```python
def test_json_store_round_trips(tmp_path):
    store = JsonStore(tmp_path / "registry.json")
    store.save({"projects": [{"id": "repo:demo"}]})
    assert store.load() == {"projects": [{"id": "repo:demo"}]}


def test_missing_store_returns_default(tmp_path):
    assert JsonStore(tmp_path / "missing.json").load(default={"projects": []}) == {"projects": []}
```

- [ ] **Step 2: Run `python -m pytest tests/test_storage.py -q` and confirm the expected missing-class failure.**

- [ ] **Step 3: Implement `JsonStore.load/save` with UTF-8 JSON and temp-file replacement.**

- [ ] **Step 4: Run the focused storage tests, then add `merge_manual_overrides(auto, overrides)` and test that manual fields survive a refresh.**

### Task 3: Implement time rules and read-only repository scanning

**Files:**
- Create: `src/project_manager/models.py`
- Create: `src/project_manager/scanner.py`
- Test: `tests/test_time_rules.py`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: Write failing tests for Git/file/manual creation-time precedence and repository discovery.**

```python
def test_manual_creation_time_wins():
    result = derive_creation_time("2026-01-01", "2026-02-01", "2026-03-01")
    assert result.value == "2026-03-01" and result.source == "manual"


def test_filesystem_is_estimate_without_git():
    result = derive_creation_time(None, "2026-02-01", None)
    assert result.value == "2026-02-01" and result.source == "filesystem_estimate"


def test_discover_repositories_skips_nested_noise(tmp_path):
    (tmp_path / "good" / ".git").mkdir(parents=True)
    (tmp_path / "good" / "node_modules" / ".git").mkdir(parents=True)
    assert discover_repositories(tmp_path) == [tmp_path / "good"]
```

- [ ] **Step 2: Run the scanner tests and confirm they fail for the missing functions.**

- [ ] **Step 3: Implement dataclasses for `ProjectRecord`, `CreationTime`, and `TimelineEvent`; implement bounded `os.walk` discovery, Git subprocess calls with timeouts, README purpose extraction, and `last_modified_at = max(last_commit_at, working_tree_modified_at)`.**

- [ ] **Step 4: Run scanner/time tests and a read-only smoke scan against `D:\Github`; assert that `_references` are marked reference scope and that no project status changes.**

### Task 4: Derive and persist project timelines

**Files:**
- Create: `src/project_manager/timeline.py`
- Test: `tests/test_timeline.py`

- [ ] **Step 1: Write failing tests for chronological events and source labels.**

```python
def test_timeline_orders_events_newest_first():
    events = build_timeline([
        {"type": "commit", "at": "2026-01-01", "summary": "old"},
        {"type": "validation", "at": "2026-02-01", "summary": "new"},
    ])
    assert [event.summary for event in events] == ["new", "old"]
```

- [ ] **Step 2: Run the test and confirm the missing-function failure.**

- [ ] **Step 3: Implement timeline normalization for commit, working-tree, validation, and manual events; preserve unknown dates instead of inventing them.**

- [ ] **Step 4: Run the timeline tests and persist per-project events under `<data_dir>\timeline\<project-id>.json`.**

### Task 5: Implement the Tkinter A1 dashboard

**Files:**
- Create: `src/project_manager/ui.py`
- Create: `src/project_manager/main.py`
- Test: `tests/test_ui_state.py`

- [ ] **Step 1: Write failing tests for filtering, selected-project state, and close-to-tray state transitions.**

```python
def test_close_hides_window_until_tray_exit():
    state = WindowState()
    state.request_close()
    assert state.visible is False and state.exited is False
    state.request_exit()
    assert state.exited is True
```

- [ ] **Step 2: Run the state tests and confirm the expected missing-class failure.**

- [ ] **Step 3: Implement `WindowState`, the left filter/list pane, the A1 detail pane, refresh button, and timeline renderer.**

- [ ] **Step 4: Implement `TrayController` with a generated Pillow icon; `WM_DELETE_WINDOW` calls `hide`, tray “打开看板” calls `deiconify`, and tray “退出应用” calls `destroy` and stops the icon.**

- [ ] **Step 5: Run state tests; manually launch `python -m project_manager --data-dir "D:\Program Files (x86)\ProjectManagerData"`, close the window, reopen from tray, and exit from tray.**

### Task 6: Add CLI smoke checks and documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/superpowers/specs/2026-09-05-project-management-dashboard-design.md`
- Create: `README.md`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write a failing CLI test for `--self-check` and explicit data-root reporting.**

- [ ] **Step 2: Implement `python -m project_manager --self-check --data-dir <path>` without opening a GUI; print repo root, data root, writable status, and registry counts.**

- [ ] **Step 3: Run the complete suite with `python -m pytest -q` and run the self-check against the requested D-drive directory.**

- [ ] **Step 4: Update README with development launch, data locations, tray behavior, and the fact that installer packaging is deferred.**

### Task 7: Verification checkpoint before packaging

- [ ] **Step 1:** Confirm no files under `D:\Github\Agent\*` changed except the manager workspace itself.
- [ ] **Step 2:** Confirm all runtime JSON/log files are under `D:\Program Files (x86)\ProjectManagerData` during the smoke test.
- [ ] **Step 3:** Confirm the app remains responsive after refresh errors and displays permission errors without silently falling back to C:.
- [ ] **Step 4:** Record test commands and results in `inventory/validation-results.md`; leave installer/EXE work for a separate plan.
