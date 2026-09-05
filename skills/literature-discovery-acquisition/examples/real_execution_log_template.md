# 真实执行日志模板 (Real Execution Log Template)

> **本文件是模板**，不是已完成的执行记录。每次通过本 Skill 完成一次完整或快速文献检索后，应在此目录下按 `real_execution_log_YYYY-MM-DD_<课题简称>.md` 命名归档一份真实日志。

---

## 元信息

| 字段 | 值 |
|---|---|
| 执行日期 | YYYY-MM-DD |
| 执行模式 | Deep Search / Quick Search |
| 课题描述 | （一句话） |
| Grill-Me 用户确认 | Q1=? / Q2=? / Q3=? / Q4=? |
| 执行 Agent | Claude Code / Codex / Antigravity |

---

## 检索式与命中数

| 检索式编号 | 数据源 | 检索式（完整布尔表达式） | 命中数 | 执行时间 |
|---|---|---|---:|---|
| Q01 | OpenAlex | `...` | — | — |
| Q02 | PubMed | `...` | — | — |
| Q03 | Europe PMC | `...` | — | — |
| Q04 | Web Search | `...` | — | — |

---

## 去重与初筛结果

| 阶段 | 数量 |
|---|---:|
| 原始总命中（含重复） | — |
| 四级去重后 | — |
| Include | — |
| Exclude | — |
| Uncertain | — |

---

## 引文追踪（仅 Deep Search）

| 轮次 | Seed Papers | 追踪方向 | 新增候选 | 新增 Include | 边际贡献率 |
|---|---|---|---:|---:|---:|
| Round 1 | — | Backward + Forward | — | — | —% |
| Round 2 | — | Author Chasing | — | — | —% |

---

## 饱和度收敛

| 轮次 | 本轮新增有效 | 累计有效 | 边际贡献率 | 判定 |
|---|---:|---:|---:|---|
| 初始检索 | — | — | 100% | — |
| 引文追踪 R1 | — | — | —% | — |
| 引文追踪 R2 | — | — | —% | 收敛 / 继续 |

---

## Quality Gatekeeper 审查决议

```markdown
### 🛡️ 质量审查员核验决议

- **审查状态**：[ PASS / REJECT ]
- **审计轮次**：第 ? 轮
- **核验评分卡**：
  1. 检索式布尔语法：[ PASS / ISSUE ]
  2. 概念矩阵完整度：[ PASS / ISSUE ]
  3. 初筛一致性与 Uncertain 保留：[ PASS / ISSUE ]
  4. 零幻觉与元数据真实性：[ PASS / ISSUE ]
  5. 数据源覆盖透明度：[ PASS / ISSUE ]
  6. 全文下载完整性：[ PASS / N/A ]
  7. 硕博学位论文履约：[ PASS / N/A ]
  8. PRISMA-S 合规：[ ?/16 ]
```

---

## OA 下载统计（仅 Stage 8）

| 类别 | 数量 |
|---|---:|
| OA_DOWNLOADED | — |
| PREPRINT_AVAILABLE | — |
| PAYWALLED | — |
| 魔数校验失败 | — |

---

## 经验与改进记录

> 每次真实执行后在此记录：哪些检索词出乎意料地有效/无效、哪些数据源命中率异常、初筛中遇到的边界案例、Gatekeeper 驳回的原因与修正方式。这些记录将作为 Skill 校准的实证依据。

- （待填写）
