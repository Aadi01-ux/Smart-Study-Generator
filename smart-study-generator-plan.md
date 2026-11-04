# Smart Study Generator Agent — Implementation Plan

## Top-Level Overview

Build a **greenfield multi-agent AI application** called **Smart Study Generator Agent**.
The system uses **IBM Granite 4H Small** (via IBM watsonx.ai) as the LLM for all five specialized AI agents.
A central orchestrator wires the agents together and controls which agent runs and when.
The frontend is a **Streamlit** dashboard with seven pages.

### Storage Architecture (three-tier)
| Layer | Technology | Purpose |
|---|---|---|
| In-memory | Streamlit `session_state` | Current doc, active agent outputs, live quiz state |
| Persistent structured | Local JSON files (path from `.env`) | Quiz scores, progress, study plans, flashcard results, completed topics |
| Persistent semantic | ChromaDB (path from `.env`) | Document embeddings, semantic search, RAG context for agents |

### Embedding model
ChromaDB uses its built-in **`sentence-transformers/all-MiniLM-L6-v2`** default embedding function — no extra API key required.

### Key constraints
- Single IBM Granite service shared by all five agents — no separate API keys.
- Credentials read exclusively from `.env` — never hardcoded or stored in `session_state`.
- Data paths (`CHROMA_DB_PATH`, `JSON_DATA_PATH`) configurable via `.env`.
- Python 3.12 compatible; no unnecessary frameworks.
- Multiple documents may be uploaded; all are stored simultaneously in ChromaDB — no replacement on new upload.
- Document IDs and filenames stored as ChromaDB metadata so retrieved chunks are traceable to their source.
- Duplicate detection: before embedding, check if a document with the same `doc_id` (derived from filename) already exists; skip re-embedding if so.

---

## Final Project Structure

```
smart-study-generator/
├── app.py
├── orchestrator.py
├── granite_service.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── agents/
│   ├── __init__.py
│   ├── resource_analyzer_agent.py
│   ├── study_material_agent.py
│   ├── assessment_agent.py
│   ├── study_planner_agent.py
│   └── progress_recommendation_agent.py
├── services/
│   ├── __init__.py
│   ├── document_service.py
│   ├── storage_service.py
│   └── vector_database_service.py
└── components/
    ├── __init__.py
    ├── dashboard.py
    ├── upload.py
    ├── flashcards.py
    ├── quiz.py
    └── study_planner.py
```

---

## Sub-Tasks

---

### Sub-Task 1 — Project Scaffold & Configuration

**Status:** [x] done

**Intent**
Create the skeleton of the project: all directories, empty `__init__.py` files, `requirements.txt`, `.env.example`, `.gitignore`, `config.py`, and `README.md`. This gives every subsequent sub-task a stable foundation to build on.

**Expected Outcomes**
- All directories exist with `__init__.py` files.
- `requirements.txt` lists all dependencies (streamlit, pypdf, python-dotenv, ibm-watsonx-ai, chromadb, sentence-transformers, requests).
- `.env.example` shows all ten env var keys (six required + four optional) with comments explaining defaults.
- `.gitignore` includes `.env`, `data/`, `__pycache__/`, `*.pyc`, `.venv/`.
- `config.py` reads all env vars via `python-dotenv`, exposes typed constants; required vars raise `ValueError` if missing; optional vars use sensible defaults (`MAX_TOKENS=1024`, `TEMPERATURE=0.3`, `CHUNK_SIZE=1000`, `CHUNK_OVERLAP=150`).
- `README.md` explains setup and how to run the app.

**Todo List**
1. Create `agents/`, `services/`, `components/` directories each with an empty `__init__.py`.
2. Write `requirements.txt` with all pinned or minimum-version dependencies.
3. Write `.env.example` with all ten env var placeholders (6 required + 4 optional) and inline comments.
4. Write `.gitignore`.
5. Write `config.py` — load `.env`, expose all ten constants; required ones raise `ValueError` if missing; optional ones use `int`/`float` defaults.
6. Write `README.md` with setup instructions.

**Relevant Context**
- No existing files; start from scratch.
- `.env` path constants used in Sub-Tasks 5 (storage_service) and 6 (vector_database_service).

---

### Sub-Task 2 — Granite Service

**Status:** [x] done

**Intent**
Implement `granite_service.py` — the single shared LLM client used by all five agents. All IBM watsonx.ai API calls go through this one module.

**Expected Outcomes**
- `GraniteService` class with a `generate(prompt: str, system_prompt: str, max_tokens: int = None) -> str` method.
- Uses `ibm-watsonx-ai` SDK with credentials from `config.py`; `max_tokens` defaults to `config.MAX_TOKENS`, `temperature` defaults to `config.TEMPERATURE`.
- Returns plain text response string.
- Raises a descriptive exception on API failure.
- A helper `generate_json(...)` method that calls `generate(...)` and parses the JSON response; raises `ValueError` with the raw response if parsing fails.

**Todo List**
1. Write `granite_service.py` with `GraniteService` class.
2. Implement `generate()` using the IBM watsonx.ai SDK `ModelInference` class, passing `model_id`, `credentials`, `project_id`, `MAX_TOKENS`, and `TEMPERATURE` from `config.py`.
3. Implement `generate_json()` — wraps `generate()`, strips markdown code fences if present, calls `json.loads()`, re-raises with context on failure.
4. Add a `get_granite_service()` module-level singleton factory so agents don't each instantiate their own client.

**Relevant Context**
- `config.py` from Sub-Task 1 supplies `IBM_API_KEY`, `IBM_ENDPOINT_URL`, `IBM_PROJECT_ID`, `GRANITE_MODEL_ID`.
- All five agents import `get_granite_service()` from this file.

---

### Sub-Task 3 — Document Service

**Status:** [x] done

**Intent**
Implement `services/document_service.py` — handles reading uploaded PDF and TXT files and splitting content into chunks suitable for embedding and LLM context windows.

**Expected Outcomes**
- `DocumentService` class.
- `extract_text(file_bytes: bytes, filename: str) -> str` — uses `pypdf` for PDFs, plain decode for TXT.
- `chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> list[str]` — splits into overlapping chunks; defaults to `config.CHUNK_SIZE` and `config.CHUNK_OVERLAP`.
- `generate_doc_id(filename: str) -> str` — deterministic ID derived from filename (e.g. `hashlib.md5(filename)`), used for duplicate detection in ChromaDB.
- Returns clean, stripped text (no excessive whitespace).

**Todo List**
1. Write `services/document_service.py`.
2. Implement `extract_text()` branching on file extension (`.pdf` → pypdf, `.txt` → decode).
3. Implement `chunk_text()` using a sliding-window word-based chunker with `config.CHUNK_SIZE` / `config.CHUNK_OVERLAP` defaults.
4. Implement `generate_doc_id()` using `hashlib.md5(filename.encode()).hexdigest()`.
5. Handle empty-document edge case gracefully.

**Relevant Context**
- Used by Agent 1 (`resource_analyzer_agent.py`) and `vector_database_service.py`.
- `file_bytes` comes from `st.file_uploader` in `components/upload.py`.

---

### Sub-Task 4 — Storage Service (JSON)

**Status:** [x] done

**Intent**
Implement `services/storage_service.py` — all reads and writes of persistent structured data (quiz scores, progress records, study plans, flashcard results, completed topics) go through this service.

**Expected Outcomes**
- `StorageService` class.
- Methods: `save_quiz_result()`, `load_quiz_results()`, `save_study_plan()`, `load_study_plan()`, `save_progress()`, `load_progress()`, `save_flashcard_result()`, `load_flashcard_results()`.
- Data stored in `JSON_DATA_PATH` directory (from `config.py`).
- Creates the directory if it doesn't exist.
- Each data type stored in its own file (e.g., `quiz_results.json`, `study_plan.json`, `progress.json`, `flashcard_results.json`).
- Thread-safe read-modify-write pattern using file locking or simple in-process approach.

**Todo List**
1. Write `services/storage_service.py` with `StorageService` class.
2. Implement `_load(filename)` and `_save(filename, data)` private helpers that handle JSON serialization and directory creation.
3. Implement all public methods, each calling `_load`/`_save` with the appropriate filename.
4. Add a `get_storage_service()` singleton factory.

**Relevant Context**
- `JSON_DATA_PATH` from `config.py` (Sub-Task 1).
- Used by Agent 3 (assessment), Agent 4 (planner), Agent 5 (progress/recommendation).

---

### Sub-Task 5 — Vector Database Service (ChromaDB)

**Status:** [x] done

**Intent**
Implement `services/vector_database_service.py` — manages document embeddings in a persistent local ChromaDB instance. Supports multiple simultaneous documents with metadata, duplicate detection, and semantic search across all stored content.

**Expected Outcomes**
- `VectorDatabaseService` class.
- Uses ChromaDB's built-in default embedding function (`sentence-transformers/all-MiniLM-L6-v2`).
- Persistent storage at `CHROMA_DB_PATH` (from `config.py`).
- `add_document(doc_id: str, chunks: list[str], filename: str) -> bool` — stores chunks with metadata `{"doc_id": ..., "filename": ..., "chunk_index": ...}`; returns `False` (skips) if `doc_id` already exists, `True` if newly added.
- `document_exists(doc_id: str) -> bool` — checks if any chunks for this `doc_id` are already stored.
- `search(query: str, n_results: int = 5) -> list[dict]` — returns top-N results each as `{"text": ..., "filename": ..., "doc_id": ...}` so callers know which document the chunk came from.
- `list_documents() -> list[dict]` — returns unique documents stored: `[{"doc_id": ..., "filename": ...}]`.
- `delete_document(doc_id: str) -> None` — removes all chunks for a given document.
- `clear_all() -> None` — wipes the collection.
- `get_chunk_count() -> int` — total number of chunks stored.
- Uses a single ChromaDB collection named `"study_materials"`.
- Add a `get_vector_db_service()` singleton factory.

**Todo List**
1. Write `services/vector_database_service.py`.
2. Initialize `chromadb.PersistentClient(path=CHROMA_DB_PATH)` in the constructor.
3. Use `client.get_or_create_collection("study_materials")` with the default embedding function.
4. Implement `document_exists()` — query collection with `where={"doc_id": doc_id}` and check if results are non-empty.
5. Implement `add_document()` — call `document_exists()` first; if exists return `False`; otherwise add chunks with full metadata, return `True`.
6. Implement `search()` — query collection, extract `documents` and `metadatas` from result, return list of dicts with `text`, `filename`, `doc_id`.
7. Implement `list_documents()` — retrieve all metadatas, deduplicate by `doc_id`, return list of `{doc_id, filename}`.
8. Implement `delete_document()`, `clear_all()`, `get_chunk_count()`.
9. Add `get_vector_db_service()` singleton.

**Relevant Context**
- `CHROMA_DB_PATH` from `config.py` (Sub-Task 1).
- Called by Agent 1 after document extraction to store embeddings.
- Called by Agents 2, 3, 4, 5 via the orchestrator to retrieve relevant context before prompting Granite.

---

### Sub-Task 6 — The Five Agents

**Status:** [x] done

**Intent**
Implement all five agent classes. Each agent is a Python class with a `run()` method, a system prompt, structured inputs/outputs, and error handling. All agents share the `GraniteService` singleton.

**Expected Outcomes**
Each file produces a working agent class:

| File | Class | Core output |
|---|---|---|
| `agents/resource_analyzer_agent.py` | `ResourceAnalyzerAgent` | JSON: subject, topics, subtopics, definitions, key_concepts |
| `agents/study_material_agent.py` | `StudyMaterialAgent` | JSON: notes, summaries, flashcards, simplified_concepts |
| `agents/assessment_agent.py` | `AssessmentAgent` | JSON: questions (each with options, answer, explanation); score; weak_topics |
| `agents/study_planner_agent.py` | `StudyPlannerAgent` | JSON: daily_plan list with date, topic, hours, activities |
| `agents/progress_recommendation_agent.py` | `ProgressRecommendationAgent` | JSON: strong_topics, weak_topics, milestones, recommendations, next_topic |

All agents:
- Accept `context_chunks: list[dict]` (retrieved from ChromaDB — each dict has `text`, `filename`, `doc_id`) as part of their input where applicable.
- Call `granite_service.generate_json()`.
- Validate the returned JSON has the required keys.
- Raise `ValueError` with a clear message on invalid response.

**Agent-specific ChromaDB access rules:**
- **Agent 1 (ResourceAnalyzerAgent):** WRITES chunks to ChromaDB via `add_document()`; calls Granite to produce structured analysis from the full extracted text.
- **Agent 2 (StudyMaterialAgent):** READS from ChromaDB via `search(query)` to gather relevant context before calling Granite.
- **Agent 3 (AssessmentAgent):** READS from ChromaDB via `search(topic)` for quiz generation context; does NOT write.
- **Agent 4 (StudyPlannerAgent):** Does NOT access ChromaDB directly — receives topic list and weak topics from the orchestrator.
- **Agent 5 (ProgressRecommendationAgent):** Primarily uses quiz/progress data; MAY optionally receive ChromaDB search results from the orchestrator when relevant study content is needed for recommendations.

**Todo List**
1. Write `agents/resource_analyzer_agent.py` — `ResourceAnalyzerAgent(granite_service, vector_db_service, document_service)`. `run(file_bytes: bytes, filename: str) -> dict`. Extract text, generate `doc_id`, call `vector_db_service.add_document()` (skip if duplicate), call Granite on full text for structured analysis; include `doc_id` and `filename` in output.
2. Write `agents/study_material_agent.py` — `StudyMaterialAgent(granite_service, vector_db_service)`. `run(query: str, analyzed_material: dict) -> dict`. Search ChromaDB, format context chunks with source filenames, call Granite for notes + flashcards.
3. Write `agents/assessment_agent.py` — `AssessmentAgent(granite_service, vector_db_service)`. `run(topic: str) -> dict` for quiz generation (searches ChromaDB). Separate `evaluate(questions: list, student_answers: list) -> dict` for scoring + weak topic identification.
4. Write `agents/study_planner_agent.py` — `StudyPlannerAgent(granite_service)`. `run(subject: str, exam_date: str, hours_per_day: float, topics: list, weak_topics: list) -> dict`.
5. Write `agents/progress_recommendation_agent.py` — `ProgressRecommendationAgent(granite_service, vector_db_service)`. `run(quiz_results: list, completed_topics: list, all_topics: list, context_query: str = None) -> dict`. Optionally searches ChromaDB if `context_query` is provided.
6. Verify all `__init__.py` files export the agent classes.

**Relevant Context**
- `granite_service.py` (Sub-Task 2), `vector_database_service.py` (Sub-Task 5), `storage_service.py` (Sub-Task 4), `document_service.py` (Sub-Task 3).
- Agent 1 is the only agent that writes to ChromaDB.
- Agent 3 `evaluate()` is called by the orchestrator which then writes the result to `StorageService`.
- Duplicate doc handling: Agent 1's `run()` returns `{"skipped": True, "doc_id": ...}` if the document was already embedded, with a notice shown in the UI.

---

### Sub-Task 7 — Orchestrator

**Status:** [x] done

**Intent**
Implement `orchestrator.py` — the central coordinator that instantiates all services and agents, wires their inputs/outputs together, and exposes a clean per-workflow API that `app.py` calls.

**Expected Outcomes**
- `Orchestrator` class.
- Constructor builds one each of: `GraniteService`, `VectorDatabaseService`, `StorageService`, `DocumentService`, then instantiates all five agents.
- Methods map directly to user actions:
  - `process_document(file_bytes, filename) -> dict` — runs Agent 1 (which extracts text, deduplicates, embeds in ChromaDB, calls Granite for analysis); returns full analysis dict including `doc_id`, `filename`, `skipped` flag.
  - `generate_study_material(query: str) -> dict` — Agent 1 output from `session_state` used as `analyzed_material`; orchestrator searches ChromaDB for context, runs Agent 2.
  - `generate_quiz(topic: str) -> dict` — searches ChromaDB for context, runs Agent 3 `run()`.
  - `evaluate_quiz(questions, answers) -> dict` — runs Agent 3 `evaluate()`, calls `StorageService.save_quiz_result()`, returns result.
  - `generate_study_plan(subject, exam_date, hours, topics) -> dict` — loads weak topics via `StorageService.load_progress()`, runs Agent 4, calls `StorageService.save_study_plan()`.
  - `get_progress_report() -> dict` — loads quiz history + completed topics from `StorageService`; calls Agent 5 with optional ChromaDB context if weak topics are present.
  - `list_uploaded_documents() -> list[dict]` — delegates to `VectorDatabaseService.list_documents()`.
- Each method wraps the agent call in a try/except and returns `{"error": "<message>", "agent": "<name>"}` on failure.
- Returns a result dict that always includes `{"agent_name": ..., "agent_status": "success"|"error", ...payload...}` so the UI can show which agent ran.
- Does not run agents unnecessarily.

**Todo List**
1. Write `orchestrator.py` with `Orchestrator` class.
2. Implement constructor: build `GraniteService`, `VectorDatabaseService`, `StorageService`, `DocumentService`, and all five agent instances.
3. Implement all seven workflow methods with consistent result envelope `{"agent_name": ..., "agent_status": ..., ...}`.
4. Each method catches all exceptions, logs the error, and returns the error envelope so the UI never crashes.
5. Add a `get_orchestrator()` module-level singleton.

**Relevant Context**
- All services from Sub-Tasks 2–5.
- All agents from Sub-Task 6.
- `app.py` (Sub-Task 8) will be the only caller of `Orchestrator`.

---

### Sub-Task 8 — Streamlit Dashboard

**Status:** [x] done

**Intent**
Implement the complete Streamlit frontend: `app.py` as the entry point and all six `components/` files. The UI has seven pages/sections, displays agent execution status, and surfaces multi-document awareness in the Upload page.

**Expected Outcomes**
Seven fully functional pages:
1. **Home** — project title, Agent Overview table (all five agents + responsibilities), how-to-use guide, link to upload.
2. **Upload Study Material** — `st.file_uploader` (PDF/TXT, `accept_multiple_files=True`), triggers `orchestrator.process_document()` for each file, shows per-file Agent 1 status badge, displays "Already uploaded (duplicate skipped)" when `skipped=True`, shows list of all documents currently in ChromaDB via `orchestrator.list_uploaded_documents()`.
3. **AI Study Notes** — text input for topic query, triggers `orchestrator.generate_study_material()`, shows Agent 2 notes + summaries; source filenames shown alongside each retrieved chunk.
4. **Flashcards** — card-flip UI using `session_state`, loads flashcards from `session_state["flashcards"]`.
5. **Practice Quiz** — topic input, generates quiz via `orchestrator.generate_quiz()`, renders MCQ form, submits to `orchestrator.evaluate_quiz()`, shows score + per-question explanation + weak topics list.
6. **Study Planner** — form for subject, exam date, hours/day; pre-populates weak topics from `session_state["progress"]` if available; triggers `orchestrator.generate_study_plan()`, shows Agent 4 daily plan as a table.
7. **Progress Dashboard** — calls `orchestrator.get_progress_report()`, shows Agent 5 strong/weak topics, score-over-time `st.line_chart`, milestone badges, and next-topic recommendation.

All pages:
- Show an agent status badge ("🤖 Agent X is running…" / "✅ Done") using `session_state`.
- Never display raw API credentials.
- Use `session_state` for all transient state.

**Todo List**
1. Write `components/upload.py` — multi-file uploader loop, per-file orchestrator call, duplicate notice, uploaded-documents list.
2. Write `components/dashboard.py` — home page with agent overview table and quick-start guide.
3. Write `components/flashcards.py` — card-flip UI driven by `session_state["flashcards"]`.
4. Write `components/quiz.py` — topic input, quiz generation, MCQ form, evaluation, results display with weak topics.
5. Write `components/study_planner.py` — plan generation form (pre-populated weak topics) + daily plan table output.
6. Write `app.py` — `st.sidebar` navigation, imports all components, renders selected page, initialises all `session_state` keys on first load, calls `get_orchestrator()` once and stores in `session_state`.
7. Verify Progress Dashboard renders `st.line_chart` from quiz score history and shows Agent 5 recommendations.

**Relevant Context**
- `orchestrator.py` (Sub-Task 7) is the only backend dependency for components.
- `session_state` keys to initialise: `orchestrator`, `analysis`, `uploaded_docs`, `study_material`, `flashcards`, `flashcard_index`, `quiz`, `quiz_answers`, `quiz_result`, `study_plan`, `progress`, `agent_status`.
- `components/` files are pure UI — no direct service or agent calls; all backend goes through the orchestrator.

---

## Implementation Order

```
Sub-Task 1 → Sub-Task 2 → Sub-Task 3 → Sub-Task 4 → Sub-Task 5
                                                          ↓
                                                    Sub-Task 6
                                                          ↓
                                                    Sub-Task 7
                                                          ↓
                                                    Sub-Task 8
```

Each sub-task depends on the ones above it. Sub-Tasks 3 and 4 can be built in parallel with Sub-Task 2.

---

## Data Flow Summary

1. User uploads PDF/TXT → `document_service` extracts text → `vector_db_service` embeds chunks → Agent 1 analyzes → result stored in `session_state["analysis"]`.
2. User requests study notes → orchestrator searches ChromaDB for relevant chunks → Agent 2 generates notes/flashcards → stored in `session_state["study_material"]` and `session_state["flashcards"]`.
3. User requests quiz → ChromaDB search → Agent 3 generates questions → stored in `session_state["quiz"]` → user answers → Agent 3 evaluates → `storage_service` saves result → `session_state["quiz_result"]`.
4. User requests study plan → `storage_service` loads weak topics → Agent 4 generates plan → `storage_service` saves plan → `session_state["study_plan"]`.
5. User views progress → `storage_service` loads history → Agent 5 analyzes → `session_state["progress"]`.
