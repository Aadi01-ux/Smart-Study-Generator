# Smart Study Generator 📚

An AI-powered multi-agent study assistant built with **IBM Granite** on **watsonx.ai** and **Streamlit**.

## 🤖 Agent Architecture

| Agent | Role | Output |
|---|---|---|
| 🔍 Resource Analyzer | Reads PDFs/TXT, extracts topics & definitions | Subject, topics, key concepts |
| 📝 Study Material Generator | Creates notes, summaries, flashcards | Student-friendly study material |
| ✏️ Assessment Agent | Generates MCQ quizzes, evaluates answers | Quiz questions, scores, weak topics |
| 📅 Study Planner | Personalized daily study schedule | Day-by-day timetable |
| 📊 Progress & Recommendation | Analyses quiz history, recommends next steps | Progress report, recommendations |

## 🚀 Quick Start (Local)

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/smartstudygenerator.git
cd smartstudygenerator
```

### 2. Create a virtual environment
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure credentials
```bash
cp .env.example .env
# Open .env and fill in your IBM Cloud credentials
```

Required values in `.env`:
```
IBM_API_KEY=your_ibm_api_key
IBM_ENDPOINT_URL=https://eu-de.ml.cloud.ibm.com
IBM_PROJECT_ID=your_project_id
GRANITE_MODEL_ID=ibm/granite-4-h-small
CHROMA_DB_PATH=./chroma_db
JSON_DATA_PATH=./data
```

### 5. Run the app
```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

## ☁️ Deploy on Streamlit Community Cloud

1. Push this repository to GitHub (see below).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app** → select your repo → set **Main file path** to `app.py`.
4. Under **Advanced settings → Secrets**, add all values from your `.env` file in TOML format:
   ```toml
   IBM_API_KEY = "your_key"
   IBM_ENDPOINT_URL = "https://eu-de.ml.cloud.ibm.com"
   IBM_PROJECT_ID = "your_project_id"
   GRANITE_MODEL_ID = "ibm/granite-4-h-small"
   EMBEDDING_MODEL_ID = "ibm/slate-125m-english-rtrvr-v2"
   CHROMA_DB_PATH = "/tmp/chroma_db"
   JSON_DATA_PATH = "/tmp/data"
   ```
   > ⚠️ Use `/tmp/chroma_db` and `/tmp/data` as paths on Streamlit Cloud (ephemeral filesystem).
5. Click **Deploy**.

## 📁 Project Structure

```
├── app.py                  # Streamlit entry point
├── orchestrator.py         # Coordinates all agents
├── granite_service.py      # IBM Granite / watsonx.ai client + IBM embeddings
├── config.py               # Environment variable loader
├── requirements.txt        # Python dependencies
├── .env.example            # Credentials template (copy to .env)
├── agents/
│   ├── resource_analyzer_agent.py
│   ├── study_material_agent.py
│   ├── assessment_agent.py
│   ├── study_planner_agent.py
│   └── progress_recommendation_agent.py
├── services/
│   ├── document_service.py       # PDF/TXT extraction & chunking
│   ├── vector_database_service.py # ChromaDB with IBM embeddings
│   └── storage_service.py        # JSON persistence
└── components/
    ├── upload.py
    ├── dashboard.py
    ├── flashcards.py
    ├── quiz.py
    └── study_planner.py
```

## 🔑 IBM Cloud Setup

1. Create a free account at [cloud.ibm.com](https://cloud.ibm.com).
2. Create a **watsonx.ai** project and note the **Project ID**.
3. Generate an **API key** from Manage → Access IAM → API keys.
4. Use the regional endpoint for your location (e.g. `https://eu-de.ml.cloud.ibm.com`).

## 📦 Tech Stack

- **IBM Granite** (`ibm/granite-4-h-small`) — LLM for all agents
- **IBM Slate** (`ibm/slate-125m-english-rtrvr-v2`) — Embeddings
- **ChromaDB** — Vector database for semantic search
- **Streamlit** — Web UI
- **pypdf** — PDF text extraction
