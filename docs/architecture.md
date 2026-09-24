# 架构

> **English** | [简体中文](architecture.md)

## 产品边界

`mcp-ward` 是面向 MCP 工具契约的确定性兼容性检查工具。0.1 版本作用于一份
保存下来的 `tools/list` 文档或一份规范化快照。它不会启动 MCP Server，也不
调用 LLM。

## 命令表面

```text
mcp-ward snapshot INPUT [-o OUTPUT]
mcp-ward check BASELINE CANDIDATE [--profile observe|wire|agent|strict]
mcp-ward check --baseline-ref REF:PATH --candidate INPUT
mcp-ward check BASELINE CANDIDATE --format text,json,html
mcp-ward check BASELINE CANDIDATE --lang en|zh|both
mcp-ward check BASELINE CANDIDATE --report-dir DIR
mcp-ward check BASELINE CANDIDATE --html report.html
```

退出码：

- `0`：所选 profile 接受这次变更
- `1`：至少有一条 finding 达到或超过所选卡点
- `2`：输入无效、快照无效、命令行参数无效，或 Git baseline 错误

当 `--report-dir`（或 `--html` 别名）覆盖了某个格式时，该格式会写入文件；
只有在没有文件去向时才会回显到 stdout。这让
`--format json --report-dir reports/` 可以安全地用在管道里。

## 快照契约

快照是确定性、可读的 JSON。其中不包含采集时间戳、本机路径或命令行，
因此未变动的契约会产出逐字节相同的文件。

```json
{
  "snapshot_version": 1,
  "kind": "mcp-tools",
  "tools": [
    {
      "name": "search",
      "title": "Search",
      "description": "Search indexed documents.",
      "inputSchema": {"type": "object"},
      "outputSchema": {"type": "object"},
      "annotations": {},
      "extra": {}
    }
  ]
}
```

未知的工具顶层字段会保留在 `extra` 下并参与比对，这里的变化不会被悄悄忽略。
不受支持的 schema 关键字同样会被保留并以 `unknown` 呈现；受支持的投影绝不把
无法识别的构造当作安全。

## Finding 模型

每条 finding 包含：

- 稳定的 `code`
- JSON 风格的 `path`
- `axis`：`wire`、`agent` 或 `both`
- `impact`：`breaking`、`review`、`additive`、`cosmetic` 或 `unknown`
- 简明解释和变更前／后的值

`unknown` 是 fail-closed 桶：它表示该变化落在 0.1 投影之外，而不是表示这个
变化是安全的。

工具描述被重写通常是 `agent/review`：JSON-RPC 调用仍然能跑通，但模型选择或
参数生成可能改变。工具被删除是 `wire/breaking`。

## Profile

| Profile | 拦截什么 |
|---|---|
| `wire` | 协议层破坏和 `unknown` 变化；适合生成式客户端和协议一致性检查 |
| `agent` | 协议层破坏、Agent 评审级变化和 `unknown` 变化；自主 Agent 集成的默认值 |
| `strict` | 每一条 finding，包括兼容性扩展和外观漂移 |
| `observe` | 什么都不拦；适合迁移报告 |

profile 是卡点，不是多套 diff 算法。一份规范的 finding 列表喂给所有消费方。
`unknown` 永远 fail-closed：只有 `observe` 放行。

Git baseline 只从 commit-ish 读取：取 blob 之前先用
`git rev-parse --verify <ref>^{commit}` 校验该 ref。`:path` 这样的仅索引形式
和 `0:path` 这样的 revision-zero 形式都会被拒绝。

## JSON Schema 策略

V1 实现的是一个刻意很小的 schema 投影：对象属性、必填字段、标量／数组类型
集合、enum、数组元素、数值边界、字符串边界、可空性、`additionalProperties`，
以及 schema 层的 `description`／`title`。

两个方向的存在性变化都按保守方式处理：在基线没有声明的地方新增 `type` 约束
是 `breaking`；删除已声明的 `type` 则是一条 `unknown` finding，因为此时已经
无法陈述接受集合了。

不受支持的 schema 关键字既不丢弃也不解释。`$ref` 和组合关键字（`allOf`、
`anyOf`、`oneOf`、`not`、`if`／`then`／`else`）在快照中原样保留，仅按值相等
比较；v0.1 从不解析引用。任何不受支持关键字的增删改——包括上述这些——都会
产生一条 `unknown/both` finding，所有带卡点的 profile 都会 fail-closed。
这比假装兼容要保守，是有意为之。

## 渲染

- 文本是默认的 CI 表面，不强制使用颜色。
- `--lang en|zh|both` 只影响人类可读的文本和 HTML；JSON 在任何语言模式下都
  保持稳定的机器字段和消息。`zh-CN` 之类的地区写法由
  `i18n.normalize_lang` 归一化。
- 默认 `en` 输出与引入 i18n 之前的报告逐字节兼容。英文契约由
  `tests/golden/default_en/` 锁定，只能用 `python tools/gen_golden.py` 有意
  重新生成。语言相关的改动绝不应该改变英文字节、JSON、退出码或卡点判定。
- 翻译集中在 `i18n.py`，以引擎稳定的 finding `code` 为键，而不是以英文原文
  为键。只有 mcp-ward 自己的措辞会被翻译：工具名、参数名、描述、路径和用户
  输入原样透传；没有翻译的 code 会回退到原始消息。
- JSON 稳定、可机器读取，并包含所选 profile 对应的 `exit_code`。
- HTML 是单文件自包含的，使用系统字体、无外部资源、支持明暗主题、筛选按钮可
  键盘操作，并尊重 `prefers-reduced-motion`。每个 finding 的值都是已转义的
  文本；finding 可以像其余四个标签一样携带 `unknown` 影响级别。
- 本地化文本和报告其余部分走同一个终端控制字符清理器，所以翻译不可能把转义
  序列重新带回 stdout。在 `both` 模式下，标签的中文部分会包在 `lang="zh-CN"`
  里，让屏幕阅读器切换语音。
