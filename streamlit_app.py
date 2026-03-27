import streamlit as st
import pandas as pd
import numpy as np
import json
import re
import random
import time
import duckdb
from anthropic import Anthropic

# ═══════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Analytics Agent",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════
defaults = {
    "messages": [],
    "history": [],
    "api_key": "",
    "data_loaded": False,
    "last_ack": "",
    "theme": "dark",
    "user_intensity": 0,
    "auto_intensity": 0,
    "intensity_override": False,
    "first_prompt_sent": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════
is_dark = st.session_state.theme == "dark"

if is_dark:
    bg = "#0c0f14"
    bg_secondary = "#141820"
    bg_card = "#1a1f2b"
    text_primary = "#e8eaed"
    text_secondary = "#8b919e"
    accent = "#6c8cff"
    accent_dim = "#2a3558"
    border = "#252a36"
    code_bg = "#111520"
    success = "#4ade80"
    warning = "#fbbf24"
    error_c = "#f87171"
else:
    bg = "#f8f9fb"
    bg_secondary = "#ffffff"
    bg_card = "#ffffff"
    text_primary = "#1a1d23"
    text_secondary = "#5f6672"
    accent = "#4361ee"
    accent_dim = "#e0e7ff"
    border = "#e2e5eb"
    code_bg = "#f1f3f5"
    success = "#16a34a"
    warning = "#ca8a04"
    error_c = "#dc2626"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

.stApp {{
    background: {bg};
    font-family: 'Outfit', sans-serif;
    color: {text_primary};
}}
section[data-testid="stSidebar"] {{
    background: {bg_secondary};
    border-right: 1px solid {border};
}}
section[data-testid="stSidebar"] * {{
    font-family: 'Outfit', sans-serif;
    color: {text_primary};
}}
.stChatMessage {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.93rem;
    line-height: 1.65;
    background: transparent !important;
    border: none !important;
}}
.stChatMessage code {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    background: {code_bg};
}}
.mode-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: {text_secondary};
}}
.pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 10px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    font-weight: 500;
}}
.pill-retrieve {{ background: {accent_dim}; color: {accent}; }}
.pill-suggest {{ background: {"#1a2e1a" if is_dark else "#e6f4e6"}; color: {success}; }}
.pill-explore {{ background: {"#2e2a1a" if is_dark else "#fef3c7"}; color: {warning}; }}
.pill-reason {{ background: {"#2e1a2a" if is_dark else "#fce7f3"}; color: {"#c084fc" if is_dark else "#a855f7"}; }}
.transition-msg {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: {text_secondary};
    padding: 4px 0;
    margin-bottom: 4px;
    font-style: italic;
}}
.about-box {{
    background: {bg_card};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 16px;
    font-size: 0.85rem;
    line-height: 1.6;
    color: {text_secondary};
}}
.about-box a {{ color: {accent}; text-decoration: none; }}
.about-box a:hover {{ text-decoration: underline; }}
.streamlit-expanderHeader {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: {text_secondary};
}}
#MainMenu {{visibility: hidden;}}
footer {{visibility: hidden;}}
header {{visibility: hidden;}}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════
@st.cache_data
def load_data():
    orders = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_orders_dataset.csv")
    order_items = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_order_items_dataset.csv")
    products = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_products_dataset.csv")
    customers = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_customers_dataset.csv")
    payments = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_order_payments_dataset.csv")
    sellers = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_sellers_dataset.csv")
    reviews = pd.read_csv("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_order_reviews_dataset.csv")
    return {
        "orders": orders, "order_items": order_items, "products": products,
        "customers": customers, "payments": payments, "sellers": sellers, "reviews": reviews
    }

@st.cache_data
def load_schema():
    with open("data_model.json", "r") as f:
        return json.dumps(json.load(f), indent=2)

# ═══════════════════════════════════════════════════════════
# AGENT FUNCTIONS
# ═══════════════════════════════════════════════════════════
MODE_NAMES = {0: "Retrieve", 1: "Suggest", 2: "Explore", 3: "Reason"}
MODE_DESC = {
    0: "Quick factual answers. No follow-ups.",
    1: "Answer + suggest one follow-up direction.",
    2: "Answer + proactively run supplementary queries.",
    3: "Deep reasoning with advanced model. Focused analysis.",
}
MODE_PILLS = {0: "pill-retrieve", 1: "pill-suggest", 2: "pill-explore", 3: "pill-reason"}
TRANSITIONS = {
    (0,1): "Switching to Suggest — will offer a useful follow-up direction.",
    (0,2): "Switching to Explore — will proactively analyze adjacent dimensions.",
    (0,3): "Switching to Reason — engaging advanced model for reliable analysis.",
    (1,0): "Switching to Retrieve — quick factual answer.",
    (1,2): "Switching to Explore — broadening the analysis scope.",
    (1,3): "Switching to Reason — engaging advanced model for deeper analysis.",
    (2,0): "Switching to Retrieve — narrowing to a quick answer.",
    (2,1): "Switching to Suggest — focused answer with follow-up direction.",
    (2,3): "Switching to Reason — engaging advanced model for deeper analysis.",
    (3,0): "Switching to Retrieve — quick factual answer.",
    (3,1): "Switching to Suggest — lighter analysis with follow-up.",
    (3,2): "Switching to Explore — broadening scope with supplementary queries.",
}
ACK_OPTIONS = ["Got it", "Sure", "OK", "On it", "Let me check",
               "Right", "Understood", "Will do", "Looking into it", "One moment"]

def infer_intensity(question, history):
    reasoning = [
        "explain", "why is", "why are", "why do", "why did", "why was", "why were",
        "what drives", "what drove", "drivers behind", "drivers of", "driven by",
        "what caused", "what causes", "what factors", "what leads to", "what led to",
        "how do you explain", "root cause", "interpret", "implications",
        "relationship between", "compare and explain", "reason for", "reasons for",
        "what does this mean", "what can we conclude",
        "assess the impact", "evaluate the effect", "account for",
        "correlat", "causal", "contribute to", "contributing"
    ]
    exploratory = [
        "tell me about", "overview", "broadly", "comprehensive",
        "deep dive", "in depth", "thorough", "explore",
        "what can you tell me", "break down everything",
        "full picture", "all aspects", "walk me through"
    ]
    analytical = [
        "analyze", "analyse", "assess", "evaluate", "investigate",
        "propose", "compare", "trend", "pattern", "distribution",
        "break down", "breakdown"
    ]

    q = question.lower()
    min_i, peak = 0, 0

    if history:
        min_i = 1
        peak = max(h.get("intensity", 0) for h in history)
        simple = any(p in q for p in ["how many","what is the","list","count","total",
                     "average","sum","which has the most","top 5","top 10","what percentage","show me"])
        if not simple:
            min_i = max(min_i, peak - 1)

    if any(re.search(p, q) for p in reasoning):
        return max(3, min_i), "deep reasoning required"
    if any(p in q for p in exploratory):
        return max(2, min_i), "exploratory question"
    if any(p in q for p in analytical):
        return max(1, min_i), "analytical question"

    if history:
        if len(history) >= 4 and min_i < 2:
            if all(h.get("intensity", 0) >= 1 for h in history[-3:]):
                return 2, "sustained conversation"
        if len(history) >= 2:
            words = set()
            for h in history[-3:]:
                words.update(h["question"].lower().split())
            if len(words) > 20:
                return max(2, min_i), "expanding scope"

    return min_i, "follow-up" if min_i > 0 else None

def get_model(i):
    return "claude-opus-4-6" if i == 3 else "claude-sonnet-4-6"

def get_scope(i):
    return {0:0, 1:1, 2:2, 3:1}.get(i, 0)

def llm(prompt, model="claude-sonnet-4-6", retries=3):
    client = Anthropic(api_key=st.session_state.api_key)
    for attempt in range(retries):
        try:
            r = client.messages.create(model=model, max_tokens=4096,
                                       messages=[{"role":"user","content":prompt}])
            return r.content[0].text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < retries-1:
                time.sleep(15)
            else:
                raise e

def classify(question, schema, tables, model):
    text = llm(f"""You are a data analyst assistant.

DATA MODEL:
{schema}

Available tables: {list(tables.keys())}

A user asked: {question}

Classify into one of three categories:
- can_answer: the data model is sufficient. Includes questions about the data model itself.
- cant_answer: requires data not in the model.
- clarifications_needed: too vague or ambiguous.
IMPORTANT: If no concrete metric specified and can't be inferred, classify as clarifications_needed.
Also clarifications_needed if assumptions make the answer trivially uniform.

Respond EXACTLY:
CLASSIFICATION: <can_answer|cant_answer|clarifications_needed>
REASON: <REQUIRED. Explain specifically.>""", model=model)

    c, r = "can_answer", ""
    for line in text.split("\n"):
        if line.startswith("CLASSIFICATION:"): c = line.split(":")[1].strip().lower()
        if line.startswith("REASON:"): r = line.split(":",1)[1].strip()
    return c, r

def plan(question, schema, tables, scope, model):
    scope_map = {
        0: "Generate ONLY minimum queries to directly answer. No extras.",
        1: "Generate queries to directly answer. No supplementary queries.",
        2: "Generate direct answer queries + 2-3 supplementary queries for context."
    }
    text = llm(f"""You are a data analyst. Break down the question into queries.

DATA MODEL:
{schema}

Available tables: {list(tables.keys())}
User question: {question}

{scope_map.get(scope, scope_map[0])}

You have access to the DATA MODEL documentation. Use it for metadata questions.

For each query provide label, type (primary/supplementary), and SQL (DuckDB). No semicolons.

Respond using XML:
<query><label>...</label><type>primary</type><code>SELECT ...</code></query>""", model=model)

    queries = []
    for block in re.findall(r'<query>(.*?)</query>', text, re.DOTALL):
        l = re.search(r'<label>(.*?)</label>', block, re.DOTALL)
        t = re.search(r'<type>(.*?)</type>', block, re.DOTALL)
        c = re.search(r'<code>(.*?)</code>', block, re.DOTALL)
        if l and c:
            queries.append({"label":l.group(1).strip(),
                          "type":t.group(1).strip() if t else "primary",
                          "code":c.group(1).strip().rstrip(";"),
                          "result":None, "error":None})

    ep = llm(f"""Summarize this analysis plan briefly.
User question: {question}
Queries: {chr(10).join([f"- [{q['type']}] {q['label']}" for q in queries])}
Format: INTENT: ... / QUERIES: ... / APPROACH: ...
No markdown.""", model=model)
    return queries, ep

def execute(queries, tables):
    for q in queries:
        try:
            con = duckdb.connect()
            for n, df in tables.items(): con.register(n, df)
            q["result"] = con.execute(q["code"].replace("```","").strip().rstrip(";")).df().to_string(index=False)
            con.close()
        except Exception as e:
            q["error"] = str(e)
    return queries

def narrate(question, queries, scope, intensity, schema, model):
    results = ""
    for q in queries:
        results += f"\n[{q['type'].upper()}] {q['label']}\n"
        results += f"Result:\n{q['result']}\n" if q["result"] else f"Error: {q['error']}\n"

    scope_rules = {
        0: "Answer in 1-3 sentences. Precise numbers with thousand separators. No follow-ups.",
        1: "Answer directly with precise numbers. End with exactly ONE follow-up: 'Would you like me to [specific action] next?'",
        2: "Answer directly, then supplementary findings starting with 'If you're interested in [topic],'. End with ONE follow-up."
    }
    return llm(f"""Compose a user-friendly answer from these query results.

User question: {question}
DATA MODEL: {schema}
Query results: {results}

Format: {scope_rules.get(scope, scope_rules[0])}

Rules:
- Use DATA MODEL for metadata questions
- No currency/unit assumptions unless in data model
- No adjectives like good/bad/impressive
- No query details or table names
- No filler phrases like "Based on the query results"
- NEVER infer customer intent from patterns
- Follow-up suggestions must be answerable with available data
- Frame follow-ups as descriptive, not causal

Answer:""", model=model)

def agent(question, schema, tables, intensity=0):
    model = get_model(intensity)
    scope = get_scope(intensity)

    try:
        c, reason = classify(question, schema, tables, model)
    except Exception as e:
        return {"stage1":"error","answer":None,"code":"","queries":[],"execution_plan":None,
                "narrative":f"Classification failed: {e}","intensity":intensity,"error":str(e)}

    if c == "cant_answer":
        a = f"Can't answer based on the available data. ({reason})"
        return {"stage1":"cant_answer","answer":a,"code":"","queries":[],
                "execution_plan":None,"narrative":a,"intensity":intensity,"error":None}
    if c == "clarifications_needed":
        a = f"Please clarify: {reason}"
        return {"stage1":"clarifications_needed","answer":a,"code":"","queries":[],
                "execution_plan":None,"narrative":a,"intensity":intensity,"error":None}

    try:
        queries, ep = plan(question, schema, tables, scope, model)
    except Exception as e:
        return {"stage1":"can_answer","answer":None,"code":"","queries":[],
                "execution_plan":None,"narrative":f"Planning failed: {e}","intensity":intensity,"error":str(e)}

    queries = execute(queries, tables)
    primary = [q["result"] for q in queries if q["type"]=="primary" and q["result"]]
    raw = "\n".join(primary) if primary else "No results"
    code = "\n\n".join([f"-- {q['label']}\n{q['code']}" for q in queries])

    try:
        n = narrate(question, queries, scope, intensity, schema, model)
    except Exception as e:
        n = f"(Narrative failed: {e})"

    return {"stage1":c,"answer":raw,"code":code,"queries":queries,
            "execution_plan":ep,"narrative":n,"intensity":intensity,"error":None}

def resolve(question, history):
    if not history: return question, False
    ctx = "\n".join([f"User: {h['question']}\nBot: {h['narrative'][:200]}...{h['narrative'][-200:]}" for h in history[-3:]])
    r = llm(f"""Given this conversation:

{ctx}

The user now says: {question}

If bot suggested a follow-up and user affirms, rewrite as that question.
If referencing previous exchange, rewrite as standalone.
Short metric follow-ups apply to MOST SPECIFIC entity discussed.
If standalone, return unchanged.
Return ONLY the rewritten question.""")

    clean = r.strip()
    for p in ["rewritten question:","standalone question:","rewritten:","question:"]:
        if clean.lower().startswith(p): clean = clean[len(p):].strip()
    clean = clean.strip('"').strip("'")
    return clean, clean.lower() != question.strip().lower()

# ═══════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<h2 style='margin:0;font-weight:700;letter-spacing:-0.5px;'>◆ Analytics Agent</h2>", unsafe_allow_html=True)

    with st.expander("ℹ️ About"):
        st.markdown(f"""
<div class="about-box">
<strong>Analytics Agent</strong> — AI-powered natural language analytics over Brazilian ecommerce data.<br><br>
<strong>Data:</strong> Olist dataset (~100k orders, 2016–2018). 7 tables: orders, products, customers, sellers, payments, reviews.<br><br>
<strong>Key feature:</strong> 3-way classification gate — refuses to answer when data is missing, preventing hallucinations.<br><br>
<strong>Modes:</strong><br>
• <strong>Retrieve</strong> — quick factual answers<br>
• <strong>Suggest</strong> — answer + follow-up direction<br>
• <strong>Explore</strong> — proactive supplementary analysis<br>
• <strong>Reason</strong> — deep reasoning (Opus model)<br><br>
<strong>Developer:</strong> <a href="https://www.linkedin.com/in/evgenihasin/" target="_blank">Evgeni Hasin</a> · <a href="https://github.com/ehasin" target="_blank">GitHub</a>
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    api_key = st.text_input("🔑 Anthropic API Key", type="password", value=st.session_state.api_key,
                            help="Get yours at console.anthropic.com")
    if api_key: st.session_state.api_key = api_key

    st.markdown("---")
    theme = st.radio("Theme", ["🌙 Dark","☀️ Light"], index=0 if is_dark else 1, horizontal=True)
    new_theme = "dark" if "Dark" in theme else "light"
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()

    st.markdown("---")
    if st.button("🗑️ Clear conversation"):
        for k in ["messages","history"]: st.session_state[k] = []
        for k in ["auto_intensity","user_intensity"]: st.session_state[k] = 0
        st.session_state.intensity_override = False
        st.session_state.first_prompt_sent = False
        st.rerun()

    st.markdown("---")
    st.markdown(f"<div style='font-size:0.7rem;color:{text_secondary};line-height:1.5;'>"
                f"Sonnet 4.6 · Opus 4.6 for Reason<br>Olist · ~100k orders · 2016–2018</div>",
                unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
if not st.session_state.api_key:
    st.markdown(f"""<div style="max-width:600px;margin:80px auto;text-align:center;">
    <h1 style="font-weight:700;letter-spacing:-1px;">◆ Analytics Agent</h1>
    <p style="color:{text_secondary};font-size:1rem;margin-bottom:32px;">
    Natural language analytics over Brazilian ecommerce data.</p>
    <p style="color:{text_secondary};font-size:0.88rem;">Enter your Anthropic API key in the sidebar to begin.</p>
    </div>""", unsafe_allow_html=True)
    st.stop()

try:
    tables = load_data()
    SCHEMA = load_schema()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# Mode slider
c1, c2, c3 = st.columns([1,6,1])
with c1: st.markdown(f"<div style='text-align:right;padding-top:28px'><span class='mode-label'>Fast</span></div>", unsafe_allow_html=True)
with c2:
    sv = st.select_slider("Mode", options=[0,1,2,3], value=st.session_state.user_intensity,
                          format_func=lambda x: MODE_NAMES[x],
                          help=" · ".join([f"{MODE_NAMES[i]}: {MODE_DESC[i]}" for i in range(4)]),
                          label_visibility="collapsed")
    if sv != st.session_state.user_intensity:
        st.session_state.user_intensity = sv
        st.session_state.intensity_override = True
with c3: st.markdown(f"<div style='padding-top:28px'><span class='mode-label'>Deep</span></div>", unsafe_allow_html=True)

ci = st.session_state.user_intensity if st.session_state.intensity_override else st.session_state.auto_intensity
st.markdown(f"<div style='text-align:center;margin-bottom:12px;'><span class='pill {MODE_PILLS[ci]}'>{MODE_NAMES[ci]}</span> "
            f"<span style='font-size:0.72rem;color:{text_secondary};'>{MODE_DESC[ci]}</span></div>", unsafe_allow_html=True)

# Suggestions
if not st.session_state.first_prompt_sent:
    st.markdown(f"<div style='max-width:640px;margin:20px auto;text-align:center;'>"
                f"<p style='color:{text_secondary};font-size:0.88rem;margin-bottom:16px;'>Try asking:</p></div>",
                unsafe_allow_html=True)
    suggestions = [
        "How many unique customers?",
        "Total revenue by payment type",
        "Highest 1-star review rate category",
        "What is our cost structure?",
        "Overview of available data"
    ]
    cols = st.columns(len(suggestions))
    for i, s in enumerate(suggestions):
        with cols[i]:
            if st.button(s, key=f"sug_{i}", use_container_width=True):
                st.session_state.first_prompt_sent = True
                st.session_state.messages.append({"role":"user","content":s})
                st.rerun()

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("transition"):
            st.markdown(f"<div class='transition-msg'>{msg['transition']}</div>", unsafe_allow_html=True)
        if msg.get("ack"):
            st.markdown(f"<div class='transition-msg'>{msg['ack']}</div>", unsafe_allow_html=True)
        st.markdown(msg["content"])
        if msg.get("details"):
            with st.expander("◆ Query details"):
                st.code(msg["details"]["code"], language="sql")
                if msg["details"].get("ep"): st.caption(msg["details"]["ep"])

# Chat input
if prompt := st.chat_input("Ask a question about the data..."):
    st.session_state.first_prompt_sent = True
    with st.chat_message("user"): st.markdown(prompt)
    st.session_state.messages.append({"role":"user","content":prompt})

    with st.chat_message("assistant"):
        with st.spinner(""):
            resolved, rewritten = resolve(prompt, st.session_state.history)

        ack_text = None
        if rewritten:
            ack = random.choice([a for a in ACK_OPTIONS if a != st.session_state.last_ack])
            st.session_state.last_ack = ack
            short = resolved[:80].rstrip("?").lower()
            if len(resolved) > 80: short += "..."
            ack_text = f"{ack}, will {short}."

        if st.session_state.intensity_override:
            ni = st.session_state.user_intensity
        else:
            ni, _ = infer_intensity(prompt, st.session_state.history)
            st.session_state.auto_intensity = ni

        prev_i = st.session_state.history[-1]["intensity"] if st.session_state.history else 0
        transition = None
        if ni != prev_i and st.session_state.history:
            transition = TRANSITIONS.get((prev_i, ni), f"Switching to {MODE_NAMES[ni]}.")

        if transition:
            st.markdown(f"<div class='transition-msg'>{transition}</div>", unsafe_allow_html=True)
        if ack_text:
            st.markdown(f"<div class='transition-msg'>{ack_text}</div>", unsafe_allow_html=True)

        with st.spinner(f"Analyzing ({MODE_NAMES[ni]})..."):
            r = agent(resolved, SCHEMA, tables, intensity=ni)

        st.markdown(r["narrative"])

        if r.get("code") and r["code"]:
            with st.expander("◆ Query details"):
                st.code(r["code"], language="sql")
                if r.get("execution_plan"): st.caption(r["execution_plan"])

    details = {"code":r.get("code",""),"ep":r.get("execution_plan")} if r.get("code") else None
    st.session_state.messages.append({
        "role":"assistant","content":r["narrative"],
        "transition":transition,"ack":ack_text,"details":details
    })
    st.session_state.history.append({
        "question":prompt,"resolved":resolved,
        "narrative":r["narrative"],"intensity":ni
    })
    st.rerun()
