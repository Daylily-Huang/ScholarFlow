# Context Resolution Layer: Conflict Resolution Rules

> **Status**: Production Standard  
> **Applicability**: Automated arbitration of divergent parameters across context sources

---

## 1. 跨层级冲突解决准则 (Cross-Layer Conflict)

当不同优先级层级的数据源提供冲突的参数值时，系统执行确定性优先级裁决：

```text
高优先级层级数值 (Higher-layer Value)  ---> 自动采纳生效
低优先级层级数值 (Lower-layer Value)   ---> 标记为 Overridden 记录在审计轨迹中
```

### 记录格式示例：
```yaml
target_population:
  value: All age groups (including pediatric)
  status: RESOLVED_FROM_USER
  provenance:
    source_type: current_user_message
    overrides:
      previous_value: Adults (18-65) only
      source_type: project_file
      reference: protocol_2023.md
```

---

## 2. 同层级冲突解决准则 (Equal-Layer Conflict)

当同一优先级层级中（例如两个同级的项目说明文档，或上传的两个平行表格）出现截然不同的参数设置时：

1. **时间戳优先判定**：若文件具备明确的版本号或最后修改时间戳（Last-Modified），优先采纳最新版本；
2. **无法判定时间戳时的仲裁**：
   - 系统**严禁擅自猜测或随机选择一个数值**；
   - 该变量的状态强制标记为 `UNRESOLVED_CONFLICT`；
   - 自动生成一个聚焦的 Stage 0B Grill-Me 问题，列出两个冲突数值及其出处，请用户一键裁决。

### 同层级冲突提问示范：
```markdown
### 问题: 样本量基线裁决 (`UNRESOLVED_CONFLICT`)
- **冲突说明**: 检测到项目资料中存在参数分歧：
  - `protocol_v1.md` 标注总样本量为 120 例；
  - `screening_summary.xlsx` 标注总样本量为 135 例。
- **请您裁决**:
  - **[A] (Recommended)** 采纳 135 例 (来自表格，数据精度与汇总更新鲜) `[中置信度]`
  - **[B]** 采纳 120 例 (严格按早期方案书设定)
  - **[C]** 自定义输入当前实际有效样本量
```
