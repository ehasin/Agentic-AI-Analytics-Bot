# 📊 Analytics Bot

A 3-phase AI analytics agent that takes natural language questions, classifies them, generates SQL, and returns factual narrative answers. Built with Claude Sonnet 4.6.

**[Try the live demo →](https://analytics-bot.streamlit.app)** *(deploy your own — see below)*

---

## How It Works

```
User Question → Classification → Query Planning → SQL Execution → Narrative Answer
```

### Phase 1: Classification (the key reliability feature)
Every question is classified before any query runs:
- **can_answer** — data exists, proceed
- **cant_answer** — hard stop. Explains what's missing. No guessing.
- **clarifications_needed** — question is vague or would produce meaningless results

The `cant_answer` path is the most important feature. The bot refuses to answer rather than hallucinate.

### Phase 2: Query Planning & Execution
Complex questions are broken into multiple independent SQL queries. Each runs separately — one failure doesn't kill the whole answer. Supports DuckDB SQL against in-memory DataFrames.

### Phase 3: Narrative
Results are synthesized into a concise, factual answer. No editorializing, no unfounded assumptions, no inferring customer intent from data patterns.

---

## Features

- **3-way classification gate** with detailed refusal explanations
- **Multi-turn conversation** with follow-up resolution (understands "break that down by state", "yes", "avg value?")
- **Auto depth inference** — switches to detailed analysis when it detects analytical intent
- **Manual depth control** — type `fast` or `deep` to override
- **Metadata awareness** — can answer questions about the data model itself
- **Anti-speculation rules** — states what the data shows, never infers why
- **Trivial question detection** — catches tautological and analytically meaningless questions

---

## Test Results

43/43 test cases passed across 5 difficulty categories:

| Category | Questions | Passed |
|----------|-----------|--------|
| Easy | 10 | 10 ✅ |
| Hard | 10 | 10 ✅ |
| Misleading | 10 | 10 ✅ |
| Multi-stage | 5 | 5 ✅ |
| Realistic business | 8 | 8 ✅ |

---

## Quick Start

### Option 1: Streamlit Cloud (easiest)
1. Fork this repo
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Deploy from your fork
4. Enter your Anthropic API key in the sidebar

### Option 2: Local
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Option 3: Colab
Open `Agentic_AI_Analytics_Bot_v1_4.ipynb` in Google Colab and follow the cells.

---

## Files

| File | Purpose |
|------|---------|
| `streamlit_app.py` | Interactive web app |
| `data_model.json` | Schema definition (single source of truth) |
| `Agentic_AI_Analytics_Bot_v1_4.ipynb` | Development notebook with eval harness |
| `analytics_bot_requirements_v2.md` | Production requirements spec |
| `test_results/` | Markdown files with all test outputs |

---

## Data

Uses the [Olist Brazilian Ecommerce](https://github.com/olist/work-at-olist-data) public dataset (~100k orders, 2016-2018). Data loads automatically from GitHub on first run.

---

## Architecture

The bot relies on a `data_model.json` file that describes all tables and columns in a flat structure — each table and column has a single `description` field containing business context, join guidance, use cases, and warnings. This is the single source of truth for what the bot can and cannot answer.

For production deployment (e.g., Slack integration with a real data warehouse), see `analytics_bot_requirements_v2.md` for the full specification including conversation layer rules, depth auto-inference triggers, and narrative formulation guidelines.

---

## License

MIT
