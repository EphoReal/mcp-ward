# 路线图

> **English** | [简体中文](roadmap.md)

## 0.1 — 确定性离线检查工具

- 规范化原始 `tools/list` JSON 和已有快照
- 稳定的快照输出
- 输入／输出工具 schema diff
- 描述、标题、标注和未知字段变化
- 四个消费方 profile
- 文本、JSON 和自包含 HTML 报告
- 双语人类可读报告（`--lang en|zh|both`）与语言中立的 JSON
- 通过 `git show` 读取 Git ref baseline
- 标准库测试套件和跨平台 CI

## 0.2 — 证据与易用性

- 适配器之后的可选 stdio 传输
- 面向项目自定义卡点的策略配置文件
- SARIF 输出
- 取自开源 MCP Server 的真实兼容性固件
- 带显式评审流程的 baseline 提升命令

## 更后期——只有当使用量证明有必要时

- trace 记录和确定性重放
- 基于同一 finding 模型的 OpenAPI 或 function-calling 适配器
- 托管式的 baseline 历史

## 首个版本明确不做

- 云服务、登录、多租户
- React 应用或组件框架
- LLM 生成的解释
- 自动更新 baseline
- 声称提供符合规范的 JSON Schema 校验
