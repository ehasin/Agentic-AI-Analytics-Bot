# ◆ Analytics Agent

An AI-powered analytics agent that takes natural language questions, classifies them, generates SQL, and returns factual narrative answers. Built with Claude Sonnet 4.6 and Opus 4.6.

---

## How It Works

```
User Question → Classification → Query Planning → SQL Execution → Narrative Answer
```

### Phase 1: Classification
Every question is classified before any query runs:
- **can_answer** — data exists, proceed
- **cant_answer** — hard stop. Explains what's missing. No guessing.
- **clarifications_needed** — question is vague or would produce meaningless results

### Phase 2: Query Planning & Execution
Complex questions are broken into multiple independent SQL queries (DuckDB). Each runs separately — one failure doesn't kill the whole answer.

### Phase 3: Narrative
Results are synthesized into concise, factual answers. No editorializing, no unfounded assumptions.

---

## Analysis Modes

The agent operates in 4 intensity modes, selectable via slider or auto-inferred from your questions:

| Mode | Model | Behavior |
|------|-------|----------|
| **Retrieve** | Sonnet 4.6 | Quick factual answers. No follow-ups. |
| **Suggest** | Sonnet 4.6 | Answer + suggest one follow-up direction. |
| **Explore** | Sonnet 4.6 | Answer + proactively run supplementary queries. |
| **Reason** | Opus 4.6 | Deep reasoning with advanced model. Focused analysis. |

The mode auto-adjusts based on question complexity, conversation depth, and detected user intent. Manual override is always available via the slider.

---

## Features

- **3-way classification gate** with detailed refusal explanations
- **Multi-turn conversation** with follow-up resolution
- **4-level intensity system** — auto-infers or manually controlled
- **Automatic model switching** — Opus for deep reasoning, Sonnet for everything else
- **Dark/Light theme**
- **Metadata awareness** — answers questions about the data model itself
- **Anti-speculation rules** — states what the data shows, never infers why
- **Trivial question detection** — catches tautological and meaningless questions

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

### Streamlit Cloud (easiest)
1. Fork this repo
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Deploy from your fork → point to `streamlit_app.py`
4. Enter your Anthropic API key in the sidebar

### Local
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Colab
Open `Agentic_AI_Analytics_Bot_v1_5.ipynb` in Google Colab and follow the cells.

---

## Files

| File | Purpose |
|------|---------|
| `streamlit_app.py` | Interactive web app (dark/light theme, mode slider, chat) |
| `data_model.json` | Schema definition — single source of truth |
| `Agentic_AI_Analytics_Bot_v1_5.ipynb` | Development notebook with eval harness |
| `analytics_bot_requirements_v2.md` | Production requirements spec |
| `test_results/` | Markdown files with all test outputs |

---

## Data

Uses the [Olist Brazilian Ecommerce](https://github.com/olist/work-at-olist-data) public dataset (~100k orders, 2016-2018). Data loads automatically from GitHub on first run.

---

## Architecture

The agent relies on `data_model.json` — a flat JSON schema where each table and column has a single `description` field containing business context, join guidance, use cases, and warnings. This is the single source of truth for what the agent can and cannot answer.

For production deployment (Slack integration, real data warehouse), see `analytics_bot_requirements_v2.md`.

---

## Author

**Evgeni Hasin** — [LinkedIn](https://www.linkedin.com/in/evgenihasin/) · [GitHub](https://github.com/ehasin)

---

## License

MIT
