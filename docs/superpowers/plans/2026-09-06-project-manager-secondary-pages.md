# Project Manager 二级页面实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 将 A 方案浏览器演示中的“时间线”和“扫描记录”导航做成可切换、可操作的页面，同时保持项目总览页的交互不变。

**Architecture:** 在现有单页 demo 中保留总览页作为默认页面，增加两个独立的页面容器；左侧导航只切换页面可见性，时间线页面从演示项目数据生成事件列表，扫描记录页面展示只读扫描状态和证据边界。设置页仍显示占位提示。

**Tech Stack:** HTML/CSS/原生 JavaScript、现有本地 Brainstorm Companion 服务。

---

### Task 1: 增加时间线页面

**Files:**
- Modify: `.superpowers/brainstorm/20260905-ui-beauty/content/ui-style-a-interactive-v3.html`

- [ ] **Step 1:** 增加全局时间线页面容器，显示项目筛选、事件类型筛选和按时间倒序排列的事件卡片。
- [ ] **Step 2:** 点击时间线事件时更新右侧事件详情并提示来源（git、filesystem、manual、validation）。

### Task 2: 增加扫描记录页面和页面切换

**Files:**
- Modify: `.superpowers/brainstorm/20260905-ui-beauty/content/ui-style-a-interactive-v3.html`

- [ ] **Step 1:** 增加扫描记录页面，展示扫描根目录、最后扫描时间、仓库数量、只读边界和最近一次扫描结果。
- [ ] **Step 2:** 将左侧导航改为真正的页面切换；项目总览、时间线、扫描记录可切换，设置页显示“后续开发”。

### Task 3: 验证演示页面

- [ ] **Step 1:** 验证服务根路径返回 200，并包含三个页面容器和页面切换脚本。
- [ ] **Step 2:** 验证 JavaScript 语法，重新打开浏览器演示页供用户验收。
