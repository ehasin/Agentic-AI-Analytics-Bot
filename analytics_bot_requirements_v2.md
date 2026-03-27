# Analytics Bot — Change Requests & Requirements

---

## 1. Three-Way Classification (Phase 1)

Integrate a 3-way classification step before any query execution. This is the single most important reliability feature — we prefer the bot refuses to answer rather than producing misleading results.

**Classifications:**

- `can_answer` — data model is sufficient, including metadata-only questions (e.g. "what use cases does the payments table support?")
- `cant_answer` — required data is missing. Bot must explain specifically what IS available and what is missing. This is a hard stop — no clarification loop, no workaround. The user must reformulate.
- `clarifications_needed` — question is too vague, or contains assumptions that make the answer trivially meaningless

**Why `cant_answer` matters:**
We explicitly do NOT want a clarification loop where the user can nudge the bot into answering a fundamentally unanswerable question. If the data doesn't exist, the answer is "no" — not "let me try a different angle." This prevents hallucinations and maintains trust.

**Classification prompt (tested, production-ready):**

```
You are a data analyst assistant.

DATA MODEL:
{schema}

Available tables: {list of table names}

A user asked: {question}

Classify into one of three categories:
- can_answer: the data model is sufficient to answer this question. This includes questions about the data model itself (what tables exist, what columns mean, what use cases are supported).
- cant_answer: requires data not in the model. Reasons: question_domain_mismatch, missing_data, other
- clarifications_needed: too vague or ambiguous

IMPORTANT: If no concrete metric or KPI is specified, and a clear KPI cannot be inferred from the context or available metadata, classify as clarifications_needed.

Also classify as clarifications_needed if the question contains assumptions that would make the answer trivially uniform or analytically meaningless (e.g., "profit margin assuming COGS is X% of price" produces identical margins for every category). In such cases, keep the explanation to 1-2 sentences and suggest one alternative question. Do not explain the math or why it's trivial — the user understands, they may have just phrased it differently than intended.

Respond in EXACTLY this format:
CLASSIFICATION: <can_answer|cant_answer|clarifications_needed>
REASON: <REQUIRED. If cant_answer: explain specifically which tables and columns ARE available and which are missing. If clarifications_needed: explain what the user needs to specify. If can_answer: briefly state which tables and columns will be used, or which parts of the data model documentation answer the question.>
```

---

## 2. Narrative Formulation (Phase 3)

After query execution, synthesize results into a user-friendly answer. The narrative layer must be strictly factual — no editorializing, no unfounded assumptions.

**Depth parameter:**
- `depth=0` — Direct answer only, 1-3 sentences. No supplementary analysis or follow-up suggestions. This proved sufficient for all 43 test cases.
- `depth=1` — Direct answer plus 2-3 supplementary queries for context (trends, breakdowns, related metrics). Ends with one suggested follow-up question. Implemented and available but not yet required as default.

**Narrative prompt (tested, production-ready):**

```
Compose a user-friendly analytical answer from these query results.

User question: {question}

DATA MODEL (use for metadata questions about table structure, use cases, column meanings):
{schema}

Query results:
{formatted results from all executed queries}

Format rules (depth=0):
- Answer in 1-3 sentences, one per primary query result
- State precise numbers with thousand separators
- If the question has multiple parts, address each part clearly
- Do not add context, interpretation, or follow-up suggestions

Format rules (depth=1):
- Start with a direct answer using primary query results, precise numbers with thousand separators
- Address every part of the user's question explicitly
- Weave in supplementary findings naturally, each as its own short paragraph starting with "If you're interested in [topic],"
- Use precise numbers first, approximations only after
- Skip any queries that failed silently
- End with one suggested follow-up question: "Would you like me to analyze [specific topic] next?"

General rules:
- Access to DATA MODEL documentation is available. Use it to answer questions about table structure, use cases, column meanings — weave metadata and query results together naturally
- When referencing metadata, present as facts without quoting documentation verbatim
- Do not assume currency or units unless explicitly in the results or data model
- Do not use adjectives to characterize results as good/bad/impressive/concerning/significant/remarkable
- Do not show query details, table names, or column names
- Do not repeat raw data verbatim — synthesize into readable prose
- If a query was meant to explain "why" something is the case, provide the explanation using the data
- Do not start sentences with filler phrases like "Based on the query results", "Analysis reveals", "The data shows that"
- It IS acceptable to reference the data source mid-sentence for trust, e.g. "Credit cards account for 78% of revenue (103,886 payments)"
- If query results show no meaningful variation (identical values across all rows), flag this to the user and suggest how to reformulate for more useful analysis
```

---

## 3. Query Planning (Phase 2)

The bot should break complex questions into multiple independent queries. Each query gets a label, a type (primary/supplementary), and is executed independently so one failure doesn't kill the whole answer.

**Key behaviors:**
- For metadata-only questions (about the schema itself), the bot should answer from documentation directly without generating queries
- For mixed questions (metadata + data), generate queries for data parts and answer metadata parts from documentation
- Multi-part questions should produce one query per part
- depth=1 adds 2-3 supplementary queries automatically based on inferred user intent

**Execution plan output:**
Each response should include a brief execution plan describing:
- INTENT: perceived user intent (one sentence)
- QUERIES: what each query answers
- APPROACH: how results will be synthesized

This is valuable for debugging and for building user trust.

---

## 4. Model

Confirmed: use latest Sonnet (currently 4.6). Same pricing across Sonnet versions, better instruction-following and coding consistency on 4.6.

---

## 5. Response Structure

Each bot response should contain:
- `stage1`: classification result (can_answer / cant_answer / clarifications_needed)
- `answer`: raw query output
- `code`: all SQL queries executed (labeled)
- `execution_plan`: intent + queries + approach
- `narrative`: user-facing formatted answer
- `error`: error details if any step failed

For Slack: display `narrative` as the main message. Offer `code` and `execution_plan` as optional expandable details or thread replies.

---

## 6. Data Model Schema

The bot relies on a JSON schema file (`data_model.json`) that describes all available tables and columns. The schema uses a simple, flat structure:

**Structure:**
- Each table has a `table_name` and a `description` attribute
- Each column within a table has a `column_name`, `data_type`, and `description` attribute
- There are no separate structured attributes for relationships, use cases, or join guidance — all of this is packed into the `description` field as free text

**What goes into table descriptions:**
- What the table represents and its grain (one row per what)
- USE FOR / DO NOT USE FOR guidance
- Join guidance (which tables to join on which columns, and when)
- Relationship info (e.g. "Join to orders ON order_id for order context. One order can have multiple payment rows.")
- Warnings and gotchas

**What goes into column descriptions:**
- What the column means in business terms
- Data type and format notes (e.g. "Format: YYYY-MM-DD HH:MM:SS. Convert with pd.to_datetime()")
- Join role (e.g. "Foreign key to orders table" or "Primary key")
- Known issues (e.g. "Column name has a typo: 'lenght' instead of 'length'")
- Units and currency where applicable (e.g. "Price in BRL (Brazilian Real)")

**Why this matters:**
The schema is the single source of truth for what the bot can and cannot answer. The quality of descriptions directly determines classification accuracy (Phase 1) and query correctness (Phase 2). The bot reads descriptions as text — it does not parse structured relationship arrays — so packing all guidance into descriptions is both simpler to maintain and equally effective. The lean approach with a single description attribute is critical for maintenance and keeping the model up to date with occasional Data Product updates. We will not be able to support a more elaborate structure with multiple attributes, nor it is required per the successful tests with this approach.

---

## Additional

I will provide:
1. The full prototype workbook was provided
2. The data_model.json schema file for the TCT MVP was provided (named main_schema.json at the time)
3. 50 Test cases tailored for the TCT domain were provided
