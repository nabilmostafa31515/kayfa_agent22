# 🎓 Kayfa AI Sales Agent

A production-ready agentic AI sales assistant for [Kayfa](https://kayfa.io) — built with LangGraph, RAG, MongoDB Atlas, and Streamlit.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🤖 Agentic AI | LangGraph multi-node workflow |
| 📚 RAG Pipeline | FAISS + SentenceTransformers (multilingual) |
| 🌍 Bilingual | Arabic (RTL) + English — auto-detected |
| 💾 CRM | MongoDB Atlas lead storage + CRUD |
| 📊 CRM Dashboard | Plotly analytics — scores, statuses, trends |
| 📈 Performance Dashboard | Manager view — WoW KPIs, conversion funnel & quality trends |
| 🔐 Manager Login | Single sign-in (env/secrets) gating both dashboards |
| 🎯 Lead Scoring | Rule-based qualifier (0.0 → 1.0) |
| 🔒 No Hallucinations | Answers only from KB context |

---

## 🏗️ Architecture

```
User Message
    ↓
Intent Detection Node  ── detects stage, language, lead score
    ↓
Knowledge Retrieval Node  ── FAISS similarity search (k=5)
    ↓
Agent Node  ── GPT-4o + 6 tools (search_courses, search_roadmaps,
               retrieve_policy, save_lead, get_lead, update_lead)
    ↓
Lead Qualification Check  ── score ≥ 0.45 → show capture form
    ↓
CRM Save  ── MongoDB Atlas (leads collection)
    ↓
Final Response (streamed to Streamlit)
```

---

## 📁 Project Structure

```
kayfa_agent/
├── app.py                        # Entry point
├── requirements.txt
├── .env.example
│
├── data/
│   ├── json/
│   │   ├── kayfa_courses.json    # 48 courses
│   │   └── kayfa_roadmaps.json   # 13 roadmaps
│   └── text/                     # 12 markdown KB files
│
├── src/
│   ├── rag/
│   │   ├── loader.py             # Load all KB docs
│   │   ├── chunker.py            # RecursiveCharacterTextSplitter
│   │   ├── embeddings.py         # paraphrase-multilingual-MiniLM-L12-v2
│   │   └── vectorstore.py        # FAISS build + persist
│   │
│   ├── agents/
│   │   ├── sales_agent.py        # LangGraph workflow
│   │   └── lead_qualifier.py     # Scoring + intent detection
│   │
│   ├── tools/
│   │   ├── search_courses.py     # search_courses, search_roadmaps, retrieve_policy
│   │   └── save_lead.py          # save_lead, get_lead, update_lead
│   │
│   ├── database/
│   │   ├── mongodb.py            # Atlas connection manager
│   │   └── crm_repository.py     # Full CRUD + analytics aggregations
│   │
│   └── prompts/
│       └── system_prompt.py      # System + sales prompts
│
└── pages/
    ├── 1_Chat_Assistant.py       # Bilingual chat UI + lead form
    └── 2_CRM_Dashboard.py        # Lead management + Plotly charts
```

---

## 🗄️ MongoDB Schema

A lead is a full sales **ticket**, grouped into Who / What they want / How likely / What happened:

```json
{
  "_id": "ObjectId",

  // WHO
  "name": "Ahmed Mohamed",
  "phone": "01012345678",
  "whatsapp": "01012345678",
  "email": "ahmed@example.com",
  "location": "Cairo, Egypt",
  "language": "arabic",
  "dialect": "مصري",
  "contact_channel": "whatsapp",
  "best_contact_time": "بعد 6 مساءً",

  // WHAT THEY WANT
  "interest_area": "AI / Data Science",
  "products_of_interest": ["AI Diploma", "Data Science Track"],
  "recommended_product": "AI Diploma",
  "goal": "تغيير مساره المهني إلى الذكاء الاصطناعي",
  "current_level": "beginner",
  "prerequisites": "أساسيات بايثون",

  // HOW LIKELY
  "lead_score": 0.75,
  "temperature": "hot",
  "buying_signals": ["سأل عن السعر", "طلب رابط التسجيل"],
  "budget_sensitivity": "high",
  "objections": "غير متأكد من الوقت المتاح",

  // WHAT HAPPENED
  "conversation_summary": "سأل عن دبلومة الذكاء الاصطناعي وسعرها...",
  "next_action": "أرسل رابط الدفع/التسجيل وتابع فوراً.",
  "status": "new",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Only `name` / `phone` / `email` are required — every other field is optional, so
partial captures still persist. `temperature` is derived from `lead_score`
(`hot ≥ 0.6 · warm ≥ 0.35 · cold`) when not explicitly set. The agent fills these
fields via the `save_lead` tool during conversation; the chat capture form and
rule-based extractors (`detect_dialect`, `detect_current_level`,
`detect_budget_sensitivity`) backfill the rest.

**Status values:** `new` → `contacted` → `qualified` → `converted` / `lost`

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/kayfa-ai-agent
cd kayfa-ai-agent
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your keys
```

```env
OPENAI_API_KEY=sk-...
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/
MONGODB_DB=kayfa_crm
```

### 3. Run

```bash
streamlit run app.py
```

The FAISS index builds automatically on first run (~30 seconds).

---

## ☁️ Deployment

### Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Add secrets from `.env` in the Secrets panel
4. Deploy `app.py`

### Render / Railway

```bash
# Start command
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

Add environment variables in the platform dashboard.

---

## 🛠️ Tech Stack

- **LLM:** OpenAI GPT-4o
- **Agent Framework:** LangGraph + LangChain
- **Embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (SentenceTransformers)
- **Vector DB:** FAISS (local, persisted)
- **Database:** MongoDB Atlas
- **UI:** Streamlit + Plotly
- **Language:** Python 3.11+

---

## 📄 License

MIT — built for the KAYEF AI Engineering Program, Week 3 Task.
