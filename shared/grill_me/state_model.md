# ScholarFlow Stage 0 State Model

> **Status**: Production Standard  
> **Applicability**: Stage 0 State Machine across all ScholarFlow skills

---

## 1. 状态定义

| 状态枚举 | 含义 | 下游执行权限 | 描述 |
|---|---|---|---|
| `STAGE0_NOT_STARTED` | 初始状态 | **禁止** | 任务刚接收，尚未解析需求与提问维度 |
| `STAGE0_UNRESOLVED` | 待决中 (首轮) | **禁止** | 已完成维度分析并向用户抛出 3~5 个高影响度问题，Agent 处于挂起等待输入状态 |
| `STAGE0_ROUND2` | 待决中 (第二轮) | **禁止** | 用户首轮反馈后仍有 `CRITICAL` 级别维度未闭环，抛出最多 2 个聚焦追问 |
| `STAGE0_CONFIRMED` | 已确认锁定 | **允许** | 全部关键维度已达成共识，生成审计快照，解锁 Stage 1 及后续计算与检索工作 |
| `STAGE0_BYPASSED` | 无头/专家绕过 | **允许** | 外部传入完整参数字典或显式 `--headless` 声明，验证关键维度无冲突后直接放行 |

---

## 2. 状态转移矩阵与守卫条件 (Guards)

```
[STAGE0_NOT_STARTED]
       |
       +---> (检测到完整显式配置) -----------------------------> [STAGE0_BYPASSED]
       |
       +---> (缺少关键维度设定) ---> 动态筛选 3~5 题 ---------> [STAGE0_UNRESOLVED]
                                                                      |
                   +--------------------------------------------------+
                   |
                   v (用户回复)
      [解析器检验 Critical 维度状态]
       |
       +---> 全部 Critical 闭环 --------------------------------> [STAGE0_CONFIRMED]
       |
       +---> 存在 Critical 未决 & round == 1 -------------------> [STAGE0_ROUND2]
       |                                                                |
       |                                                                v (用户第二轮回复)
       |                                                    [再次解析 Critical 状态]
       |                                                                |
       |                                                                +---> 全部闭环 -> [STAGE0_CONFIRMED]
       |                                                                +---> 仍未闭环 -> 强制安全默认 -> [STAGE0_CONFIRMED] (附警告)
```

### 转移守卫规则：
1. **未决守卫 (Unresolved Guard)**：
   - 当状态为 `STAGE0_UNRESOLVED` 或 `STAGE0_ROUND2` 时，Agent 环境必须拦截任何对真实学术数据库检索、论文批量下载、大模型密集抽取的工具调用。
   - 违规调用应被系统层直接阻断并抛出 `GatekeeperPolicyViolationError: Cannot execute substantive research actions before Stage 0 confirmation`。

2. **确认守卫 (Confirmation Guard)**：
   - 仅当且仅当所有标记为 `CRITICAL` 级别的维度均在 `resolutions` 字典中有明确的取值时，状态方可转入 `STAGE0_CONFIRMED`。
   - 转入 `STAGE0_CONFIRMED` 时必须同步落盘 `Protocol Snapshot`。

3. **预算硬截断守卫 (Budget Exhaustion Guard)**：
   - 最大轮次限制为 2 轮。
   - 若在第二轮结束后仍有 `CRITICAL` 维度未明确，系统禁止进入第三轮质问，必须采用对应学科透镜的“最保守安全默认值”（Conservative Safe Default）并记录在审计日志中，将状态置为 `STAGE0_CONFIRMED`，同时在输出开头打印显式警示。

---

## 3. 无头/专家调用支持 (Headless Bypass)

在批处理测试、CI/CD 流水线或专家用户指定全量参数时，允许通过以下方式绕过交互：

```python
from shared.grill_me import GrillEngine

engine = GrillEngine(skill_name="literature-discovery-acquisition", domain="biomedical")
# 预先注入全量必要参数
params = {
    "D1": "开题调研",
    "D2": "mRNA疫苗对变异株中和抗体滴度衰减规律",
    "D4": "人类临床试验, 队列研究",
    "D5": "体外细胞实验, 纯动物模型",
    "D8": "2020-2024",
}
state, snapshot = engine.bypass_headless(params)
assert state == GrillState.STAGE0_BYPASSED
```

无头模式同样会生成包含 `[USER]` 与 `[SYSTEM_RULE]` 标记的 Protocol Snapshot，保持方法学审计的一致性。
