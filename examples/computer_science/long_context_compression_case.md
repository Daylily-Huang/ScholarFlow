# Cross-Disciplinary Case: Computer Science & AI

> **Research Focus**: Long-context Compression and KV-Cache Optimization for Transformer Architectures  
> **Domain Lens**: `computer_science`  
> **Workflow**: Discovery -> Evidence Extraction -> Cross-Paper Synthesis

---

## 1. Stage 0: Adaptive Grill-Me Gate

```markdown
# Stage 0 Protocol Snapshot (Computer Science)
- **Skill**: literature-discovery-acquisition
- **Domain Lens**: computer_science
- **Gate Status**: CONFIRMED

| Dimension ID | Dimension Name | Selected Setting | Provenance | Rationale |
|---|---|---|---|---|
| `D1` | 研究目标 | 基础大模型长文本处理方法学与评测综述 | `[USER]` | 聚焦机制与基准评测 |
| `D2` | 核心问题 | KV-Cache 动态剪枝对长距离检索与推理时延的权衡边界 | `[INFERRED]` | 从提示词直接提炼 |
| `D3` | 目标实体 | Transformer Decoder-only 架构族 (7B-70B 参数量) | `[USER]` | 采纳推荐方案 |
| `D4` | 纳入标准 | 必须具备开源代码、公开 Benchmark 评测及消融实验 | `[USER]` | 采纳计算机学科高复现推荐 |
| `D5` | 排除红线 | 排除未做基准对比的纯定性博客或商业宣传稿 | `[SYSTEM_RULE]` | 学术同行评审基线 |
```

---

## 2. Stage 1: Concept Matrix (Computer Science)

| Concept ID | 分类 | Core Term | Synonyms | Hierarchy / Architecture | Controlled Vocabulary |
|---|---|---|---|---|---|
| **C1** | Target System | Large Language Models | LLMs, autoregressive models | Transformer, Decoder-only, LLaMA, Mistral | ACM: Natural language generation |
| **C2** | Method | KV-Cache Compression | prompt pruning, attention sink | StreamingLLM, H2O, SnapKV, FlashAttention | IEEE: Memory management |
| **C3** | Benchmark | Long-context Benchmark | Needle in a Haystack, L-Eval | BABILong, LongBench, Ruler | ACM: Benchmark testing |
| **C4** | Outcome Metric | Retrieval Accuracy | needle recall rate, Macro-F1 | Perplexity (PPL), Time-to-First-Token (TTFT) | IEEE: Performance evaluation |

---

## 3. Evidence Extraction (Context Units: Benchmark Splits)

```markdown
| Field Name | [Context-01: LLaMA-3-8B on L-Eval] | [Context-02: LLaMA-3-8B on BABILong] | Location | Epistemic Status |
|---|---|---|---|---|
| **Compression Method** | StreamingLLM (E1) | H2O Heavy-Hitter (E1) | Section 3.2 | SUPPORTED |
| **Cache Budget** | 2048 tokens (E1) | 2048 tokens (E1) | Table 2, Page 6 | SUPPORTED |
| **Accuracy / Score** | 68.4% (E1) | 74.1% (E1) | Table 3, Page 7 | SUPPORTED |
| **Throughput Gain** | 2.8x (E2: calculated from 35ms vs 98ms) | 2.4x (E2: calculated from 41ms vs 98ms) | Section 4.1 | DERIVED |
| **Ablation Baseline** | Full Cache: 71.2% (E1) | Full Cache: 75.0% (E1) | Table 3, Page 7 | SUPPORTED |
```

---

## 4. Synthesis & Universal Boundaries

```markdown
> **核心共识命题**: 动态注意力和重度击中（Heavy-hitter）KV-Cache 剪枝在 32k 长度内可保留 95%+ 精度，同时节省 50%+ 显存。
> **共识评级**: `CONDITIONAL_CONSENSUS`
> **适用边界**:
> 1. **Entity Boundary**: 适用于预训练阶段使用了 RoPE 位置编码的自回归模型；
> 2. **Context Boundary**: 在 Needle 检索与抽取式问答上成立；在多跳因果复杂推理任务上精度出现衰减 (>8% drop)；
> 3. **Measurement Boundary**: 评测指标为 Top-1 Recall 与 ROUGE-L；
> 4. **Hardware Boundary**: 吞吐增益在 GPU 显存受限（Memory-bound）场景下显著，算力瓶颈场景不明显。
```
