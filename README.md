# 项目管理看板

Windows 本地项目管理看板，用于集中查看多个 Git 项目的用途、阶段、状态、下一步动作和证据时间线。

项目地址：<https://github.com/Tsd100/vibe-manage>

## 功能

- 扫描一个或多个项目根目录，并合并去重；
- 从 Git 提交和文件系统提取创建时间、最近提交和最近修改时间；
- 项目总览、详情、时间线和扫描记录页面；
- 人工维护用途、状态、阶段、优先级和下一步动作；
- 根据 Git remote 自动判断是否连接 GitHub，并支持在编辑窗口手动覆盖“是/否/未确认”；
- 支持筛选、排序、关注提示和可持久化的表格列宽；
- 支持浅色/深色主题、界面缩放、多项目根目录和托盘运行；
- 窗口、任务栏和托盘使用统一的“蓝色工作台”图标。

## 环境

- Windows 10/11；
- Python 3.11 或更高版本；
- Git（扫描 Git 项目时需要）；
- Pillow、pystray、pytest。

## 安装依赖

```powershell
python -m pip install -e .
```

也可以不安装项目包，直接通过 `PYTHONPATH` 运行：

```powershell
$env:PYTHONPATH = "src"
```

## 启动

```powershell
python -m project_manager `
  --repo-root "D:\Github" `
  --data-dir "D:\Program Files (x86)\ProjectManagerData"
```

开发测试时可加 `--no-tray` 禁用系统托盘。

只检查配置、目录和仓库数量，不打开窗口：

```powershell
python -m project_manager `
  --self-check `
  --repo-root "D:\Github" `
  --data-dir "D:\Program Files (x86)\ProjectManagerData"
```

## 数据与隐私

运行数据默认保存到 `D:\Program Files (x86)\ProjectManagerData`，包括：

- `inventory/`：项目注册表、扫描快照和扫描记录；
- `overrides/`：人工字段覆盖；
- `timeline/`：项目时间线；
- `settings.json`：界面和扫描配置；
- `logs/`：运行日志。

仓库中的 `inventory/` 本地扫描快照已被 Git 忽略，不会随代码上传。请在公开仓库中使用自己的数据目录，不要提交密钥、令牌或私有项目快照。

GitHub 开源属性只读取本地仓库的 Git remote，不调用 GitHub API，也不会上传项目源代码；连接到 GitHub 的私有仓库可在项目编辑窗口手动改为“否”。

## 测试

```powershell
python -m pytest -q
```

当前测试覆盖配置、JSON 存储、人工字段、GitHub remote 判断、时间规则、仓库发现、时间线、筛选、窗口/任务栏图标、托盘生命周期和 CLI 自检。

## 目录结构

```text
src/project_manager/    应用源码
tests/                  自动化测试
assets/                 Windows 图标资产
tools/                  只读扫描工具
docs/                   设计和实现说明
```

安装器、EXE 封装、代码签名和开机自启仍属于后续工作。
