# Context Resolution Layer: Provider Contract & Graceful Degradation

> **Status**: Production Interface Standard  
> **Applicability**: Multi-agent platform portability (Claude Code, Antigravity, Codex, Cursor, CLI)

---

## 1. ContextProvider 抽象接口

为了适配不同智能体运行环境（有的平台拥有完整文件系统检索能力，有的平台仅具备当前对话与附件），ScholarFlow 将上下文获取解耦为独立的 Provider 组件：

```text
                     ContextResolver
                            │
       ┌──────────────┬─────┴────────┬──────────────┐
       │              │              │              │
  Conversation    Attachment      Upstream       Project
    Provider       Provider       Artifact       Search
                                  Provider      Provider
```

### 核心接口契约：
- `resolve_facts(task_description: str, unresolved_dims: List[str]) -> List[ContextFact]`
- `is_available() -> bool`
- `provider_type -> ContextSourceType` (`current_user`, `conversation`, `current_attachments`, `upstream_outputs`, `project_search`)

---

## 2. 优雅降级机制 (Graceful Degradation)

当某一个 Provider 不可用时（例如在无本地文件访问权限的轻量 Web 聊天窗口中）：
1. **静默跳过不可用 Provider**：系统记录 `provider.is_available() == False`，不抛出异常崩溃；
2. **状态平滑回退**：无法从该层获取的变量自然保持在 `UNRESOLVED` 状态；
3. **由 Grill-Me 自动承接**：对真正关键的未决变量，回退为在 Stage 0B 中向用户提出带 `(Recommended)` 的决策问题，确保全平台零配置平稳运行。
