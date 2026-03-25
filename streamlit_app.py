import streamlit as st
import pandas as pd
import numpy as np
import json
import re
import random
import time
import duckdb
from anthropic import Anthropic

# ─── Page Config ───
st.set_page_config(
    page_title="Analytics Bot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS ───
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');

.stApp {
    font-family: 'DM Sans', sans-serif;
}

/* Chat messages */
.stChatMessage {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.95rem;
    line-height: 1.6;
}

/* Code blocks in chat */
.stChatMessage code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #0e1117;
}

section[data-testid="stSidebar"] .stMarkdown {
    font-family: 'DM Sans', sans-serif;
}

/* Status badges */
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    font-family: 'JetBrains Mono', monospace;
}
.status-can-answer { background: #1a3a2a; color: #4ade80; }
.status-cant-answer { background: #3a1a1a; color: #f87171; }
.status-clarification { background: #3a2a1a; color: #fbbf24; }

/* Depth indicator */
.depth-indicator {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 4px;
    background: #1e293b;
    color: #94a3b8;
}
</style>
""", unsafe_allow_html=True)

# ─── Data Loading (cached) ───
@st.cache_data
def load_data():
    orders = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_orders_dataset.csv")
    order_items = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_order_items_dataset.csv")
    products = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_products_dataset.csv")
    customers = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_customers_dataset.csv")
    payments = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_order_payments_dataset.csv")
    sellers = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_sellers_dataset.csv")
    reviews = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_order_reviews_dataset.csv")
    
    tables = {
        "orders": orders,
        "order_items": order_items,
        "products": products,
        "customers": customers,
        "payments": payments,
        "sellers": sellers,
        "reviews": reviews
    }
    return tables

@st.cache_data
def load_schema():
    with open("data_model.json", "r") as f:
        data_model = json.load(f)
    return json.dumps(data_model, indent=2)

# ─── Agent Functions ───
def get_llm_client():
    return Anthropic(api_key=st.session_state.api_key)

def call_llm(prompt, max_retries=3):
    client = get_llm_client()
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(15)
            else:
                raise e

def classify_question(question, schema, tables):
    prompt = f"""You are a data analyst assistant.

DATA MODEL:
{schema}

Available tables: {list(tables.keys())}

A user asked: {question}

Classify into one of three categories:
- can_answer: the data model is sufficient to answer this question. This includes questions about the data model itself (what tables exist, what columns mean, what use cases are supported).
- cant_answer: requires data not in the model. Reasons: question_domain_mismatch, missing_data, other
- clarifications_needed: too vague or ambiguous
IMPORTANT: If no concrete metric or KPI is specified, and a clear kpi can not be inferred from the context or available metadata, classify as clarifications_needed.
Also classify as clarifications_needed if the question contains assumptions that would make the answer trivially uniform or analytically meaningless (e.g., "profit margin assuming COGS is X% of price" produces identical margins for every category). In such cases, keep the explanation to 1-2 sentences and suggest one alternative question. Do not explain the math or why it's trivial — the user understands, they may have just phrased it differently than intended.

Respond in EXACTLY this format:
CLASSIFICATION: <can_answer|cant_answer|clarifications_needed>
REASON: <REQUIRED. If cant_answer: explain specifically which tables and columns ARE available and which are missing. If clarifications_needed: explain what the user needs to specify. If can_answer: briefly state which tables and columns will be used, or which parts of the data model documentation answer the question.>"""

    text = call_llm(prompt)
    classification = "can_answer"
    reason = ""
    for line in text.split("\n"):
        if line.startswith("CLASSIFICATION:"):
            classification = line.split(":")[1].strip().lower()
        if line.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return classification, reason

def plan_queries(question, schema, tables, depth):
    if depth == 0:
        depth_instruction = "Generate ONLY the minimum queries needed to directly answer the user's question. No additional context or analysis."
    else:
        depth_instruction = "First, generate queries to directly answer the user's question. Then, assess the user's likely intent and add 2-3 supplementary queries that provide useful context."

    prompt = f"""You are a data analyst. Break down the user's question into a structured analysis plan.

DATA MODEL:
{schema}

Available tables: {list(tables.keys())}

User question: {question}

{depth_instruction}

You also have direct access to the DATA MODEL documentation above. If the question asks about table descriptions, use cases, column meanings, or data model structure, you can reference that documentation directly in your labels.

For each query, provide:
- A short label describing what this query answers
- Whether it's "primary" (directly answers the question) or "supplementary" (adds context)
- The SQL (DuckDB syntax) query

Rules for queries:
- Standard SQL compatible with DuckDB
- Use CAST(column AS TIMESTAMP) for date conversions
- Use DuckDB date functions (DATE_PART, DATEDIFF, etc.)
- No semicolons
- Each query must be independently executable
- Only use tables and columns from the data model
- Do not assume currency, units, or external data not in the model

Respond using XML tags:
<query>
<label>What this query answers</label>
<type>primary</type>
<code>
SELECT ...
</code>
</query>

Generate as many query blocks as needed."""

    text = call_llm(prompt)
    queries = []
    query_blocks = re.findall(r'<query>(.*?)</query>', text, re.DOTALL)
    for block in query_blocks:
        label_match = re.search(r'<label>(.*?)</label>', block, re.DOTALL)
        type_match = re.search(r'<type>(.*?)</type>', block, re.DOTALL)
        code_match = re.search(r'<code>(.*?)</code>', block, re.DOTALL)
        if label_match and code_match:
            queries.append({
                "label": label_match.group(1).strip(),
                "type": type_match.group(1).strip() if type_match else "primary",
                "code": code_match.group(1).strip().rstrip(";"),
                "result": None,
                "error": None
            })

    plan_prompt = f"""Summarize the analysis plan in natural language.

User question: {question}
Depth: {"Direct answer only" if depth == 0 else "Direct answer plus contextual analysis"}

Queries planned:
{chr(10).join([f"- [{q['type']}] {q['label']}" for q in queries])}

Write a brief execution plan in this format:
INTENT: <one sentence describing the perceived user intent>
QUERIES: <comma-separated list of what each query answers>
APPROACH: <one sentence on how results will be synthesized>

No markdown, no extra text."""

    execution_plan = call_llm(plan_prompt)
    return queries, execution_plan

def execute_queries(queries, tables):
    for q in queries:
        try:
            con = duckdb.connect()
            for name, df in tables.items():
                con.register(name, df)
            code = q["code"].replace("```", "").strip().rstrip(";")
            result_df = con.execute(code).df()
            q["result"] = result_df.to_string(index=False)
            con.close()
        except Exception as e:
            q["error"] = str(e)
    return queries

def format_narrative(question, queries, depth, schema):
    results_text = ""
    for q in queries:
        results_text += f"\n[{q['type'].upper()}] {q['label']}\n"
        if q["result"]:
            results_text += f"Result:\n{q['result']}\n"
        else:
            results_text += f"Error: {q['error']}\n"

    if depth == 0:
        format_instruction = """Format rules:
- Answer in 1-3 sentences, one per primary query result
- State precise numbers with thousand separators
- If the question has multiple parts, address each part clearly
- Do not add context, interpretation, or follow-up suggestions"""
    else:
        format_instruction = """Format rules:
- Start with a direct answer to the user's question using primary query results, precise numbers with thousand separators
- Address every part of the user's question explicitly
- Then weave in supplementary findings naturally, each as its own short paragraph starting with "If you're interested in [topic],"
- Use precise numbers first, approximations only after
- Skip any queries that failed silently
- End with one suggested follow-up question: "Would you like me to analyze [specific topic] next?"
- The suggested question should be naturally related but different from what was already covered"""

    prompt = f"""Compose a user-friendly analytical answer from these query results.

User question: {question}

DATA MODEL (use for metadata questions about table structure, use cases, column meanings):
{schema}

Query results:
{results_text}

{format_instruction}

General rules:
- You have access to the DATA MODEL documentation above. Use it to answer questions about table structure, use cases, column meanings, or data model capabilities directly
- When referencing metadata, present as facts without quoting documentation verbatim
- Do not assume currency or units unless explicitly in the results
- Do not use adjectives to characterize results as good/bad/impressive/concerning
- Do not show query details, table names, or column names
- Do not repeat raw data verbatim — synthesize into readable prose
- Do not start sentences with filler phrases like "Based on the query results", "Analysis reveals", "The data shows that"
- It IS acceptable to reference the data source mid-sentence for trust
- If the query results show no meaningful variation, flag this to the user and suggest how to reformulate
- NEVER infer customer intent, motivation, or strategy from purchasing patterns. State what the data shows but do not speculate on why. Correlation does not imply causation or intent.
- When suggesting follow-up questions, never frame them as causal ("what drives", "why do customers"). Instead frame as descriptive ("how do X differ from Y", "what are the characteristics of Z").

Answer:"""

    return call_llm(prompt)

def analyst_agent(question, schema, tables, depth=0):
    # Phase 1: Classify
    try:
        classification, reason = classify_question(question, schema, tables)
    except Exception as e:
        return {"stage1": "error", "answer": None, "code": "", "queries": [],
                "execution_plan": None, "narrative": f"Classification failed: {e}", "error": str(e)}

    if classification == "cant_answer":
        answer = f"Can't answer based on the available data. ({reason})"
        return {"stage1": "cant_answer", "answer": answer, "code": "",
                "queries": [], "execution_plan": None, "narrative": answer, "error": None}

    if classification == "clarifications_needed":
        answer = f"Please clarify: {reason}"
        return {"stage1": "clarifications_needed", "answer": answer, "code": "",
                "queries": [], "execution_plan": None, "narrative": answer, "error": None}

    # Phase 2a: Plan queries
    try:
        queries, execution_plan = plan_queries(question, schema, tables, depth)
    except Exception as e:
        return {"stage1": "can_answer", "answer": None, "code": "", "queries": [],
                "execution_plan": None, "narrative": f"Query planning failed: {e}", "error": str(e)}

    # Phase 2b: Execute queries
    queries = execute_queries(queries, tables)

    primary_results = [q["result"] for q in queries if q["type"] == "primary" and q["result"]]
    raw_answer = "\n".join(primary_results) if primary_results else "No results"
    all_code = "\n\n".join([f"-- {q['label']}\n{q['code']}" for q in queries])

    # Phase 3: Narrate
    try:
        narrative = format_narrative(question, queries, depth, schema)
    except Exception as e:
        narrative = f"(Narrative failed: {e})"

    return {
        "stage1": classification, "answer": raw_answer, "code": all_code,
        "queries": queries, "execution_plan": execution_plan,
        "narrative": narrative, "error": None
    }

def resolve_followup(question, history, schema, tables):
    """Resolve follow-up questions into standalone questions."""
    if not history:
        return question, False
    
    recent = history[-3:]
    context = "\n".join([
        f"User: {h['question']}\nBot: {h['narrative'][:200]}...{h['narrative'][-200:]}"
        for h in recent
    ])
    
    resolved = call_llm(f"""Given this conversation history:

{context}

The user now says: {question}

If the bot's last message ended with a suggested follow-up question and the user responds with "yes", "sure", "go ahead", "please do", or similar affirmation, rewrite it as that suggested follow-up question.

If this is a follow-up that references the previous exchange (e.g. "break that down by state", "same but for 2017", "why?"), rewrite it as a complete standalone question that includes all necessary context.

When the user asks a short follow-up about a metric (e.g. "avg value?", "how many?", "% of total?"), apply it to the MOST SPECIFIC entity discussed, not a broader set. If the previous exchange identified a single top result, the follow-up refers to that one result, not the entire list.

If it's already a standalone question, return it unchanged.""")
    
    was_rewritten = resolved.strip().lower() != question.strip().lower()
    return resolved.strip(), was_rewritten

def get_action_summary(resolved_question):
    """Get a brief action summary for the acknowledgment."""
    summary = call_llm(
        f"Summarize this question as a short action phrase starting with a verb "
        f"(e.g. 'check average order value for bed products', 'analyze revenue by state'). "
        f"Max 10 words. No markdown. Question: {resolved_question}"
    )
    return summary.strip().rstrip(".").replace("**", "").lower()

def infer_depth(question, history, current_depth, auto_depth_set):
    """Infer whether to switch to deeper analysis."""
    deep_phrases = ["analyze", "analyse", "explain", "assess", "evaluate",
                    "propose", "investigate", "deep dive", "in depth",
                    "broadly", "comprehensive", "thorough", "explore",
                    "why is", "why are", "why do", "what drives",
                    "what factors", "root cause", "understand"]
    
    q_lower = question.lower()
    
    if current_depth == 0 and any(phrase in q_lower for phrase in deep_phrases):
        return 1, "phrasing"
    
    if current_depth == 0 and not auto_depth_set and len(history) >= 3:
        return 1, "conversation"
    
    return current_depth, None

# ─── Session State Init ───
if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = []
if "current_depth" not in st.session_state:
    st.session_state.current_depth = 0
if "auto_depth_set" not in st.session_state:
    st.session_state.auto_depth_set = False
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False
if "last_ack" not in st.session_state:
    st.session_state.last_ack = ""

ACK_OPTIONS = ["Got it", "Sure", "OK", "On it", "Let me check",
               "Right", "Understood", "Will do", "Looking into it", "One moment"]

# ─── Sidebar ───
with st.sidebar:
    st.markdown("## 📊 Analytics Bot")
    st.markdown("---")
    
    api_key = st.text_input("Anthropic API Key", type="password", 
                            value=st.session_state.api_key,
                            help="Get yours at console.anthropic.com")
    if api_key:
        st.session_state.api_key = api_key
    
    st.markdown("---")
    st.markdown("### Analysis Depth")
    
    depth_mode = st.radio(
        "Mode",
        ["⚡ Fast (depth=0)", "🔍 Deep (depth=1)", "🤖 Auto"],
        index=2,
        help="Fast: direct answers only. Deep: adds supplementary analysis. Auto: infers from your questions."
    )
    
    if depth_mode == "⚡ Fast (depth=0)":
        st.session_state.current_depth = 0
        st.session_state.auto_depth_set = True  # prevent auto-override
    elif depth_mode == "🔍 Deep (depth=1)":
        st.session_state.current_depth = 1
        st.session_state.auto_depth_set = True
    else:
        st.session_state.auto_depth_set = False
    
    st.markdown("---")
    st.markdown("### Current State")
    depth_label = "⚡ Fast" if st.session_state.current_depth == 0 else "🔍 Deep"
    st.markdown(f"Depth: **{depth_label}**")
    st.markdown(f"Messages: **{len(st.session_state.history)}**")
    
    st.markdown("---")
    if st.button("🗑️ Clear Conversation"):
        st.session_state.messages = []
        st.session_state.history = []
        st.session_state.current_depth = 0
        st.session_state.auto_depth_set = False
        st.session_state.last_ack = ""
        st.rerun()
    
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.7rem; color:#64748b; line-height:1.4;'>"
        "Built with Claude Sonnet 4.6<br>"
        "Data: Olist Brazilian Ecommerce<br>"
        "~100k orders · 2016-2018"
        "</div>",
        unsafe_allow_html=True
    )

# ─── Main Area ───
if not st.session_state.api_key:
    st.markdown("## 📊 Analytics Bot")
    st.markdown("Enter your Anthropic API key in the sidebar to get started.")
    st.markdown("---")
    st.markdown("""
    **What this bot does:**
    - Takes natural language questions about a Brazilian ecommerce dataset
    - Classifies whether the question can be answered, needs clarification, or requires unavailable data
    - Generates and executes SQL queries
    - Returns factual, precise narrative answers
    
    **Try asking:**
    - "How many unique customers are there?"
    - "What is the total revenue by payment type?"
    - "Which product category has the highest percentage of 1-star reviews?"
    - "What is our cost structure?" *(will correctly refuse — no cost data)*
    """)
    st.stop()

# Load data
try:
    tables = load_data()
    SCHEMA = load_schema()
    if not st.session_state.data_loaded:
        st.session_state.data_loaded = True
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.info("Make sure `data_model.json` is in the same directory as this app.")
    st.stop()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("details"):
            with st.expander("📋 Query Details"):
                st.code(msg["details"]["code"], language="sql")
                if msg["details"].get("execution_plan"):
                    st.markdown(f"**Execution Plan:**\n{msg['details']['execution_plan']}")
                st.markdown(f"**Classification:** `{msg['details']['stage1']}`")

# Chat input
if question := st.chat_input("Ask a question about the data..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})
    
    # Handle fast/deep inline commands
    manual_override = False
    if question.strip().lower().startswith("fast"):
        st.session_state.current_depth = 0
        st.session_state.auto_depth_set = False
        manual_override = True
        remaining = question.strip()[4:].lstrip(":").lstrip()
        if remaining:
            question = remaining
        else:
            with st.chat_message("assistant"):
                st.markdown("Switched to quick answer mode. ⚡")
            st.session_state.messages.append({"role": "assistant", "content": "Switched to quick answer mode. ⚡"})
            st.rerun()
    
    elif question.strip().lower().startswith("deep"):
        st.session_state.current_depth = 1
        st.session_state.auto_depth_set = False
        manual_override = True
        remaining = question.strip()[4:].lstrip(":").lstrip()
        if remaining:
            question = remaining
        else:
            with st.chat_message("assistant"):
                st.markdown("Switched to detailed analysis mode. 🔍")
            st.session_state.messages.append({"role": "assistant", "content": "Switched to detailed analysis mode. 🔍"})
            st.rerun()
    
    with st.chat_message("assistant"):
        # Follow-up resolution
        resolved_question = question
        with st.spinner("Thinking..."):
            resolved_question, was_rewritten = resolve_followup(
                question, st.session_state.history, SCHEMA, tables
            )
            
            if was_rewritten:
                ack = random.choice([a for a in ACK_OPTIONS if a != st.session_state.last_ack])
                st.session_state.last_ack = ack
                action = get_action_summary(resolved_question)
                ack_text = f"*{ack}, will {action}.*"
                st.markdown(ack_text)
            
            # Auto depth inference
            if not manual_override and not st.session_state.auto_depth_set:
                new_depth, reason = infer_depth(
                    question, st.session_state.history,
                    st.session_state.current_depth, st.session_state.auto_depth_set
                )
                if new_depth != st.session_state.current_depth:
                    st.session_state.current_depth = new_depth
                    st.session_state.auto_depth_set = True
                    if reason == "phrasing":
                        st.info("📊 Switching to detailed analysis mode based on your question. Type `fast` to switch back.")
                    else:
                        st.info("📊 You seem to be digging deeper — switching to detailed analysis mode. Type `fast` to switch back.")
        
        # Run agent
        with st.spinner("Analyzing..."):
            r = analyst_agent(resolved_question, SCHEMA, tables, depth=st.session_state.current_depth)
        
        # Display narrative
        narrative = r["narrative"]
        st.markdown(narrative)
        
        # Display details in expander
        if r.get("code") and r["code"]:
            with st.expander("📋 Query Details"):
                st.code(r["code"], language="sql")
                if r.get("execution_plan"):
                    st.markdown(f"**Execution Plan:**\n{r['execution_plan']}")
                
                badge_class = {
                    "can_answer": "status-can-answer",
                    "cant_answer": "status-cant-answer",
                    "clarifications_needed": "status-clarification"
                }.get(r["stage1"], "")
                st.markdown(
                    f'**Classification:** <span class="status-badge {badge_class}">{r["stage1"]}</span>',
                    unsafe_allow_html=True
                )
    
    # Build message content for history display
    msg_content = ""
    if was_rewritten:
        msg_content += f"*{ack}, will {action}.*\n\n"
    msg_content += narrative
    
    details = {
        "code": r.get("code", ""),
        "execution_plan": r.get("execution_plan"),
        "stage1": r.get("stage1", "")
    } if r.get("code") else None
    
    st.session_state.messages.append({
        "role": "assistant",
        "content": msg_content,
        "details": details
    })
    
    # Update conversation history
    st.session_state.history.append({
        "question": question,
        "resolved": resolved_question,
        "narrative": narrative,
        "depth": st.session_state.current_depth
    })
    
    st.rerun()
