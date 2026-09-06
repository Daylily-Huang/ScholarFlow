# External Query Privacy & Sanitization Policy

ScholarFlow enforces strict query minimization before sending requests to external public APIs and search engines (OpenAlex, Europe PMC, PubMed, Web Search).

## 1. 核心脱敏原则 (Query Minimization Principle)

When constructing search queries from project contexts or local research materials:
- **Only extract public scientific concepts**: Standard domain terminologies, published taxon/molecule names, recognized methodologies, and general research questions.
- **Strictly prohibit leaking private/local information**:
  1. Internal laboratory sample identifiers and plate well codes
  2. Unpublished research manuscripts, drafts, or internal notes
  3. Author personal credentials, API keys, passwords, or contact details
  4. Non-public project codenames or confidential institutional identifiers
  5. Raw experimental data tables or unreleased preliminary measurements

## 2. 查询安全过滤规范 (Query Sanitization Protocol)

Before invoking any external network search tool:
1. Strip all tokens matching local file paths (`file:` URI, `C:\`, `/home/`, etc.).
2. Strip private laboratory prefixes or sample barcodes.
3. Keep search query terms under standard conceptual limits (typically 3–8 scientific keywords or boolean expressions).
4. For targeted searches, use standard public identifiers (e.g., DOI, PMID, OpenAlex ID) rather than dumping full private paragraphs into the query parameter.
