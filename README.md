# 🚀 Kayfa AI Sales Agent

> **An intelligent, production-ready AI Sales Agent that understands customers, recommends the right learning path, and converts conversations into qualified CRM leads.**

Built with **LangGraph**, **RAG**, **OpenAI GPT-4o**, **MongoDB Atlas**, and **Streamlit**.

---

<p align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge)
![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20AI-blue?style=for-the-badge)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![FAISS](https://img.shields.io/badge/FAISS-Vector%20Search-red?style=for-the-badge)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)

</p>

---

# 🎯 Overview

Every day, potential learners visit educational platforms looking for the right course.

They ask questions like:

- Which diploma fits my background?
- Is this roadmap suitable for beginners?
- What's included in the price?
- Can I get a certificate?
- Which track helps me get hired faster?

Most visitors leave before speaking with a human sales representative.

This project solves that problem by building an **AI-powered Sales Agent** capable of:

- Understanding customer intent
- Answering only from a trusted knowledge base
- Recommending the best learning path
- Handling objections naturally
- Detecting buying signals
- Capturing qualified leads automatically
- Providing CRM analytics for the sales team

---

# 🎥 Live Demo

## 🌐 Live Application

👉 **https://kayfaagent22-kde7bz8fx6qkj2v9cxp9zu.streamlit.app/**

---

# ✨ Features

| Feature | Description |
|----------|-------------|
| 🤖 Agentic AI | Multi-node LangGraph workflow |
| 📚 RAG Pipeline | FAISS + SentenceTransformers |
| 🌍 Bilingual | Arabic (RTL) & English |
| 🧠 Intent Detection | Understands customer stage & goals |
| 🎯 Smart Recommendations | Courses, Tracks & Diplomas |
| 💾 MongoDB CRM | Automatic Lead Capture |
| 📊 CRM Dashboard | Interactive Plotly Analytics |
| 📈 Performance Dashboard | KPIs, Funnel & Conversion Metrics |
| 🔐 Manager Authentication | Protected Admin Dashboard |
| ⭐ Lead Qualification | Rule-Based Lead Scoring |
| 🚫 Hallucination Prevention | Responses grounded only in KB |
| ⚡ Real-time Streaming | Fast conversational experience |

---

# 🏗 System Architecture

```text
                    User Message
                         │
                         ▼
             Intent Detection Node
      (Language • Stage • Lead Score)
                         │
                         ▼
         Knowledge Retrieval (FAISS)
                         │
                         ▼
         GPT-4o Agent (LangGraph)
        ┌────────────────────────┐
        │ search_courses         │
        │ search_roadmaps        │
        │ retrieve_policy        │
        │ save_lead              │
        │ get_lead               │
        │ update_lead            │
        └────────────────────────┘
                         │
                         ▼
          Lead Qualification Engine
                         │
          score >= 0.45 ?
               /          \
             Yes          No
              │            │
              ▼            ▼
      Capture Customer   Continue Chat
              │
              ▼
      MongoDB Atlas CRM
              │
              ▼
      Streamlit Chat UI
```

---

# 🖥️ Application Screens

## 👤 Customer

- AI Chat Assistant
- Arabic & English conversations
- Smart recommendations
- Conversation memory
- Lead capture

---

## 👨‍💼 Manager Dashboard

- CRM Management
- Lead Analytics
- Conversion Funnel
- Weekly Performance
- Status Distribution
- Lead Quality
- Search & Filters

---

# 🧠 AI Workflow

The AI agent follows an intelligent multi-step workflow:

### 1️⃣ Understand User Intent

Detects:

- Language
- Dialect
- User goal
- Current experience
- Buying intent

---

### 2️⃣ Retrieve Knowledge

Uses **RAG** to search:

- Courses
- Roadmaps
- Diplomas
- Policies
- FAQs

No answers are generated without retrieved context.

---

### 3️⃣ Recommend the Best Product

Based on:

- Experience
- Career Goal
- Budget
- Learning Path

---

### 4️⃣ Qualify the Lead

Calculates a lead score between:

```
0.00 → 1.00
```

Lead Temperature:

| Score | Status |
|--------|---------|
| ≥ 0.60 | 🔥 Hot |
| 0.35–0.59 | 🟡 Warm |
| < 0.35 | ❄ Cold |

---

### 5️⃣ Save to CRM

Qualified leads are automatically stored inside MongoDB Atlas with:

- Customer Information
- Products of Interest
- Conversation Summary
- Buying Signals
- Recommended Next Action

---

# 📂 Project Structure

```text
kayfa_agent/
│
├── app.py
├── requirements.txt
├── .env.example
│
├── data/
│   ├── json/
│   └── text/
│
├── src/
│   ├── agents/
│   ├── rag/
│   ├── tools/
│   ├── database/
│   └── prompts/
│
└── pages/
    ├── Chat Assistant
    └── CRM Dashboard
```

---

# 🗄 CRM Schema

Each qualified lead contains:

### 👤 Customer

- Name
- Phone
- WhatsApp
- Email
- Country
- Language
- Dialect

---

### 🎯 Interests

- Goal
- Current Level
- Interested Products
- Recommended Product

---

### 📈 Qualification

- Lead Score
- Temperature
- Buying Signals
- Budget Sensitivity
- Objections

---

### 📝 Sales Summary

- Conversation Summary
- Next Action
- Status
- Timestamp

---

# 🚀 Quick Start

## Clone Repository

```bash
git clone https://github.com/yourusername/kayfa-ai-agent.git

cd kayfa-ai-agent
```

---

## Install

```bash
pip install -r requirements.txt
```

---

## Configure

```env
OPENAI_API_KEY=

MONGODB_URI=

MONGODB_DB=
```

---

## Run

```bash
streamlit run app.py
```

The FAISS index is automatically built during the first run.

---

# ☁ Deployment

Supports deployment on:

- ✅ Streamlit Cloud
- ✅ Railway
- ✅ Render

---

# 🛠 Tech Stack

| Category | Technology |
|------------|------------|
| LLM | OpenAI GPT-4o |
| Framework | LangGraph + LangChain |
| Retrieval | RAG |
| Embeddings | SentenceTransformers |
| Vector Store | FAISS |
| Database | MongoDB Atlas |
| Backend | Python |
| Frontend | Streamlit |
| Charts | Plotly |

---

# 💡 Key Highlights

- Production-ready architecture
- Modular LangGraph workflow
- Grounded AI responses
- CRM automation
- Smart lead qualification
- Bilingual support
- Interactive dashboards
- Scalable design
- Secure manager authentication

---

# 📈 Future Improvements

- Voice Conversations
- WhatsApp Integration
- Email Automation
- Calendar Booking
- Multi-Agent Collaboration
- AI Sales Analytics
- Human Handoff
- Cost Monitoring Dashboard
- Response Trace Visualization

---

# 🤝 Acknowledgments

This project was developed as part of the **Kayfa AI Engineering Internship Program**, demonstrating how modern Agentic AI systems can enhance customer engagement and automate sales workflows using Retrieval-Augmented Generation (RAG), Large Language Models, and CRM integration.

---

# 📬 Contact

**Mostafa Nabil**

💼 LinkedIn: *(Add your profile link)*

💻 GitHub: *(Add your GitHub profile link)*

🌐 Live Demo:

**https://kayfaagent22-kde7bz8fx6qkj2v9cxp9zu.streamlit.app/**

---

## ⭐ If you found this project interesting, don't forget to star the repository!
