# 重点期刊四层级评价体系与检索式映射指南 (Key Journal Mapping & Syntax Generation)

## 一、为什么必须建立重点期刊分级？

在学术文献检索中，期刊不是简单的一个元数据字段，而是具有三重核心功能：
1. **质量信标 (Quality Beacon)**：在数千篇搜索候选结果中，高水平期刊成果通常具有更严苛的同行评议、更可靠的方法学设计和更高的引用率，可优先作为精读标杆。
2. **引文追踪种子池 (Seed Paper Incubator)**：顶级期刊与权威综述期刊发表的论文是执行 Backward / Forward Citation Chasing（双向引文追踪）的最优质种子来源。
3. **精准过滤靶标 (Targeted Source Filter)**：在需要高精探索（Quick Search）或特定领域前沿追踪时，通过限定来源期刊（Source Filter），能瞬间排除掠夺性期刊与低质噪声。

---

## 二、四层级期刊推荐标准 (Four-Tier System)

针对任何科研主题，Skill 必须自动构建如下四层级重点期刊推荐表：

### 第一层级：顶级综合与学科旗舰 (Top Multidisciplinary & Flagship)
- **定义**：全球公认最高水准的综合类或大生命科学/自然科学顶级刊物（Nature Index 收录刊物）。
- **学术价值**：报道该领域的突破性理论、重大学科范式转变或具有普适科学意义的重大成果。
- **代表刊物**：
  - 综合顶刊：*Nature*, *Science*, *PNAS*, *Nature Communications*, *Science Advances*
  - 生命科学旗舰：*Cell*, *Current Biology*, *Nature Ecology & Evolution*
  - 计算机旗舰：*IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI)*, *ACM Computing Surveys*
  - 医学旗舰：*The New England Journal of Medicine (NEJM)*, *The Lancet*, *JAMA*

### 第二层级：主题核心与专业顶刊 (Core Specialized & Domain Leading)
- **定义**：本学科领域最权威、最被同行广泛认可、发文量与专业引用最密集的专业顶级学术期刊（通常为 JCR Q1、中科院 1 区/Top 期刊）。
- **学术价值**：承载本领域绝大部分经典实证研究、标准方法学检验与体系化研究成果。
- **代表刊物（以分子生态学/野生动物保护为例）**：
  - *Molecular Ecology*（分子生态学圣经）
  - *Conservation Biology*（保护生物学顶级刊物）
  - *Journal of Applied Ecology*（应用生态学旗舰）
  - *Ecology*（生态学学会旗舰）
  - *Biological Conservation*（经典生物保护）
  - *Heredity* / *Journal of Heredity*（群体遗传学经典）
  - *Mammal Research* / *Acta Theriologica*（哺乳动物学主流）

### 第三层级：权威综述期刊 (Authoritative Review Journals)
- **定义**：专门发表长篇、高被引系统性文献综述与领域未来展望的权威刊物。
- **学术价值**：**文献检索的战略性武器**。一篇顶级综述通常包含 100–300 篇经过严格筛选的核心文献，是进行 Backward Citation Chasing（反向引文追溯）和迅速摸清领域脉络的最快途径。
- **代表刊物**：
  - *Trends in Ecology & Evolution (TREE)*
  - *Annual Review of Ecology, Evolution, and Systematics*
  - *Biological Reviews*
  - *Nature Reviews Genetics* / *Nature Reviews Microbiology*
  - *Annual Review of Animal Biosciences*

### 第四层级：中文核心与本土权威 (Chinese Core & CSCD/PKU)
- **定义**：中国科学引文数据库（CSCD）核心库入选期刊、中文核心期刊要目总览（北大核心）期刊，或针对中国特定物种、地理生态、本土临床具有不可替代价值的权威中文学术期刊。
- **学术价值**：对于具有强地域性（如中国特有濒危野生动植物）、国内政策法律、本土流行病学或本地生态样带的研究，中文权威期刊往往保存有第一手的野外本底数据与重要调查论文。
- **代表刊物（以生态学与动物学为例）**：
  - 《兽类学报》（中国动物学会兽类学分会旗舰，中国哺乳动物非损伤取样研究基石）
  - 《生态学报》（中国生态学会旗舰）
  - 《生物多样性》（生物多样性保护旗舰）
  - 《动物学研究》(*Zoological Research*)
  - 《野生动物学报》

---

## 三、主流数据库来源过滤检索式转换规则 (Source Filter Code Blocks)

为了让用户或后续流程能够直接在各大数据库中对这些期刊实施来源限定检索，Skill 必须自动生成标准代码块：

### 1. Web of Science (WoS) 语法：`SO=(...)`
```text
SO=("Molecular Ecology" OR "Conservation Biology" OR "Journal of Applied Ecology" OR "Ecology" OR "Biological Conservation" OR "Trends in Ecology & Evolution" OR "Annual Review of Ecology Evolution and Systematics" OR "Biological Reviews")
```

### 2. PubMed / MEDLINE 语法：`[Journal]` / `[ta]`
```text
("Mol Ecol"[Journal] OR "Conserv Biol"[Journal] OR "J Appl Ecol"[Journal] OR "Ecology"[Journal] OR "Biol Conserv"[Journal] OR "Trends Ecol Evol"[Journal] OR "Biol Rev Camb Philos Soc"[Journal])
```

### 3. Scopus 语法：`EXACTSRCTITLE(...)`
```text
(EXACTSRCTITLE("Molecular Ecology") OR EXACTSRCTITLE("Conservation Biology") OR EXACTSRCTITLE("Journal of Applied Ecology") OR EXACTSRCTITLE("Ecology") OR EXACTSRCTITLE("Biological Conservation") OR EXACTSRCTITLE("Trends in Ecology and Evolution"))
```

### 4. 中国知网 (CNKI) 专业检索语法：`文献来源=(...)`
```text
(文献来源='兽类学报' OR 文献来源='生态学报' OR 文献来源='生物多样性' OR 文献来源='野生动物学报' OR 文献来源='动物学研究')
```

---

## 四、期刊限定的使用边界与反模式警示

1. **Quick Search 模式下**：允许使用期刊过滤式（Source Filter）缩小搜索范围，优先输出高可信度的核心论文；
2. **Deep Search 模式下**：**前两轮检索禁止施加期刊限定**，必须保持对所有正规刊物的开放召回，避免产生学术偏见或漏掉发表在综合新刊、专类刊上的突破性成果；期刊列表仅作为第三轮靶向补充与引文追踪种子池使用。
