# 项目管理初始资料

本目录是对 `D:\Github` 的只读盘点结果，不写入被盘点的任何项目仓库。

## 文件说明

- `projects-inventory.json`：原始扫描结果，包含路径、README、工程清单和 Git 元数据。
- `projects-inventory.md`：原始扫描结果的人类可读版本。
- `projects-status.json`：在原始数据上增加活动状态、阶段初判、下一步建议和证据完整度。
- `projects-status.md`：状态初判的人类可读版本。
- `projects-registry.json`：中央注册表草稿；`manual_*` 字段专门留给人工确认。
- `validation-results.json` / `validation-results.md`：四个重点项目的最小本地验证结果、阻塞原因和副作用核对。
- `../tools/scan_projects.ps1`：可重复运行的只读扫描器。

## 字段原则

自动字段来自 README、工程清单和 Git 元数据，只能作为线索；验证结果只覆盖明确列出的最小测试，不能直接作为项目完成度结论。

人工确认时优先补充：

1. 项目用途（它解决什么问题）；
2. 当前阶段（探索、规划、开发、维护、暂停或归档）；
3. 当前状态和下一步动作；
4. 最近一次可复现的验证证据。

## 更新方式

```powershell
& .\tools\scan_projects.ps1
```

扫描器只更新本目录中的盘点文件。后续接入 Web 看板或 Agent 更新协议时，以注册表中的人工字段和证据字段为基础。
