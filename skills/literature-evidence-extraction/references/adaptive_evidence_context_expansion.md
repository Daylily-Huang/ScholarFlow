# Adaptive Evidence Context Expansion (AECE) & Semantic Context Verification

> **Skill**: `literature-evidence-extraction`  
> **Status**: Core Grounding Standard (Epistemic Protocol)  
> **Applicability**: Universal across all academic disciplines  

---

## 1. Core Epistemic Principle: Candidate Hit ≠ Evidence

```text
Candidate Hit ≠ Evidence
Mention ≠ Relation
Co-occurrence ≠ Relation
Contextual proximity ≠ Relation
Entity evidence ≠ Claim evidence
```

> **A candidate evidence hit is only a retrieval clue. It becomes eligible evidence only after sufficient surrounding context has been examined and its semantic role has been verified against the user's target information need.**

### Execution Sequence

Skill 2 strictly enforces the execution sequence:

```text
Understand User Need
↓
Formalize Target Information Need (TIN)
↓
Locate Candidate Clues (Recall-first)
↓
Adaptive Context Expansion (AECE)
↓
Interpret Context Semantics (Semantic Role & Guards)
↓
Target Alignment Decision
↓
Structured Extraction
↓
Evidence Verification
↓
Evidence Auditor (Dimension 16)
```

**Fixed Order**: `Locate → Context → Interpret → Align → Extract`  
**Strictly Prohibited**: `Locate → Extract → (Optional Context Check)`

Context size is determined by **semantic sufficiency**, never by a fixed arbitrary character window (e.g. ±150 / ±250 chars).

---

## 2. Target Information Need (TIN)

Before candidate searching, the user's inquiry must be formalized into a structured internal representation:

```yaml
target_information_need:
  task_type: ATTRIBUTE | CLAIM | RELATION | COMPARISON | PROCEDURE | INTERPRETATION
  target_entity: optional (e.g., "Compound X", "Model A")
  target_field: optional (e.g., "sample_size", "reaction_temperature")
  target_claim: optional (e.g., "treatment increases survival")
  required_context: optional (e.g., "high temperature", "adult cohort")
  exclusion_scope: optional (e.g., "animal studies", "synthetic benchmarks")
```

**Iron Rule**: `Search Clues are retrieval aids, NOT evidence criteria.`  
Keyword hit count or token match does not establish factual truth.

---

## 3. Candidate Detection (High-Recall Phase A1)

Candidate detection focuses on high recall across:
- `TEXT_SENTENCE`
- `PARAGRAPH`
- `TABLE_ROW` / `TABLE_CELL`
- `FIGURE_CAPTION` / `FIGURE_VALUE`
- `SUPPLEMENT_ENTRY`
- `EQUATION`
- `FOOTNOTE`

A hit marks a passage as `LOCATED`. It **MUST NOT** directly jump to `EXTRACTED`.

---

## 4. Context Expansion Levels (0–6)

| Level | Name | Boundary | Purpose |
|:---|:---|:---|:---|
| **Level 0** | `EXACT_HIT` | Keyword, number, cell, phrase | Physical localization; never evidence on its own |
| **Level 1** | `SENTENCE` | Complete sentence span | Identifies subject, predicate, object, direct conditions |
| **Level 2** | `ADJACENT_SENTENCES` | Previous + Current + Next sentence | Resolves pronouns (they, this), anaphora, transitions |
| **Level 3** | `PARAGRAPH` | Enclosing paragraph | Clarifies paragraph argumentative role & definitions |
| **Level 4** | `SECTION_CONTEXT` | Enclosing Section / Subsection heading | Clarifies macroscopic discourse context |
| **Level 5** | `STRUCTURED_CONTEXT` | Table title + row + column + footnote, or Figure caption + panel + axis | Unlocks tabular & visual evidence |
| **Level 6** | `CONTEXT_UNIT` | Experiment, Cohort, Dataset, Arm | Binds evidence to isolated experimental unit |

---

## 5. Semantic Role Classification

Every candidate must be classified into its genuine functional role:

- `CURRENT_STUDY_METHOD`: Technical protocol or procedure of the current work.
- `CURRENT_STUDY_RESULT`: Direct empirical finding of the current work.
- `CURRENT_STUDY_OBSERVATION`: Descriptive observation by the authors.
- `BACKGROUND`: Introduction to established background.
- `REFERENCED_WORK`: Prior literature cited by the authors.
- `DISCUSSION_INTERPRETATION`: Speculation, hypothesis, or interpretation in discussion.
- `LIMITATION`: Study caveats, drawbacks, or scope boundaries.
- `CONTEXT_DESCRIPTION`: Environmental or setup background description.
- `COMPARATOR_CONTEXT`: Baseline or control group context.
- `OTHER_ENTITY_CONTEXT`: Findings regarding non-target entities.
- `DEFINITION`: Explicit formal conceptual definition.
- `THEORETICAL_ARGUMENT`: Deductive argumentation.
- `UNKNOWN`: Unverified role (fails closed; blocks confirmed output).

**Section Heading is a Prior, Not a Shortcut**:
Do not equate `Results` section with automatic validity, nor `Discussion` section with automatic invalidity.

---

## 6. Target Alignment Decision

After context interpretation, ScholarFlow evaluates:
> **Does this candidate actually answer the Target Information Need?**

1. **`ALIGNED`**: Directly and unambiguously answers the target question.
2. **`PARTIALLY_ALIGNED`**: Answers direction or part of the question, but leaves attributes or numeric values partial (requires uncertainty tagging).
3. **`NOT_ALIGNED`**: Mentions relevant terms, but addresses a different question, different cohort, or explicitly negates the claim.
4. **`AMBIGUOUS`**: Context is exhausted and meaning cannot be resolved without hallucination.

---

## 7. Linguistic & Epistemic Guards

1. **Negation Guard**:
   - Matches: `not, no, never, neither, nor, failed to, did not, without, non-significant`.
   - Explicit negation blocks promotion to positive relations.
2. **Modality Guard**:
   - Matches: `may, might, could, suggest, possibly, likely, speculate`.
   - Modality softens claim strength to `AUTHOR_INTERPRETATION` or requires modal qualification.
3. **Quantifier Guard**:
   - Matches: `some, most, all, subset, only, primarily`.
   - Quantifiers must be faithfully preserved to avoid overgeneralization.
4. **Condition & Scope Guard**:
   - Retains operational conditions: `under condition X`, `in subgroup A`, `at 80°C`.
5. **Comparator Guard**:
   - Retains control reference: `compared with control`, `relative to baseline`.
6. **Anti-Stitching Guard**:
   - Rejects silent joining of fragments from distant pages or incompatible sections.

---

## 8. Structured Evidence Rules

### Table Evidence
A cell value (e.g. `0.91`) must never stand alone. It must be expanded to:
`[Table Title] Row Header | Column Header | Value | Footnote`

### Figure Evidence
A visual data point must be expanded to:
`[Figure Caption] Panel Label | Axis Label | Legend | Value`

---

## 9. Stop Conditions

- **`STOP_A_MEANING_RESOLVED`**: Sufficient semantic context reached to resolve who, what, condition, and target answer.
- **`STOP_B_STRUCTURED_RESOLVED`**: Table or figure header context fully assembled.
- **`STOP_C_CONTEXT_EXHAUSTED`**: Reasonable boundaries reached without resolving ambiguity → Output `AMBIGUOUS`.

---

## 10. Intermediate Object: CandidateContextRecord

Before producing an `EvidenceRecord`, candidates pass through the intermediate contract:
`CandidateContextRecord` (`schemas/candidate_context_record.schema.json`).

Only when `decision.eligible_for_extraction == true` may the candidate be extracted into an `EvidenceRecord`.

---

## 11. Auditor Checklist: Dimension 16 (Context Sufficiency Audit)

Evidence Auditor performs the 8-point check:
1. `[ ]` Not keyword-only extraction (quote is substantive).
2. `[ ]` Full semantic unit read (at least full sentence).
3. `[ ]` Expanded to adjacent/paragraph when pronouns or anaphora exist.
4. `[ ]` Structured context (table row/col headers, figure caption) verified.
5. `[ ]` Semantic role classified (not `UNKNOWN`).
6. `[ ]` Context unit or cohort explicitly anchored.
7. `[ ]` Confirmed to answer the Target Information Need.
8. `[ ]` Free of long-distance cross-context stitching.
