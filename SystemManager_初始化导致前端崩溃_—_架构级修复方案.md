# SystemManager 初始化导致前端崩溃 — 架构级修复方案

## Core Features

- 前端 Boot Orchestrator 分层启动管线

- 日志/告警组件延迟启动与主线程安全更新

- Qt 原生时间处理（QDateTime）消除类型与兼容性问题

- 六大模块统一按需加载 + 动态导入（避免导入副作用）

## Tech Stack

{
  "Web": {
    "arch": "react",
    "component": null
  }
}

## Design

MainWindow 统一改为占位 + on_all_ready 后动态导入实例化，彻底切断顶层导入副作用；配合 BootOrchestrator 的 backend_ready/ui_ready/ui_visible 三条件触发。

## Plan

Note: 

- [ ] is holding
- [/] is doing
- [X] is done

---

[X] Step1_现状与崩溃点分析提案

[X] Step2_日志采集与函数栈定位

[X] Step3_引入BootOrchestrator与就绪协议骨架

[X] Step4_SystemManager安全加载改造（延迟导入完成）

[X] Step5_其余模块接入Orchestrator与适配层

[/] Step6_联调与回归测试（启动稳定性与降级路径验证）
