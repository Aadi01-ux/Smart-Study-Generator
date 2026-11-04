import streamlit as st
from orchestrator import get_orchestrator
from components.dashboard import render_home, render_notes, render_progress
from components.upload import render_upload
from components.flashcards import render_flashcards
from components.quiz import render_quiz
from components.study_planner import render_study_planner

st.set_page_config(
    page_title="Smart Study Generator",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state initialization ──────────────────────────────────────────────
defaults = {
    "orchestrator": None,
    "analysis": None,            # Result from Agent 1
    "uploaded_docs": [],         # List from list_uploaded_documents()
    "study_material": None,      # Result from Agent 2
    "flashcards": [],            # List of {question, answer} dicts
    "flashcard_index": 0,        # Current flashcard index
    "show_answer": False,        # Whether answer is visible on current card (legacy)
    "flashcard_submitted": False,# Whether the user has submitted their typed answer
    "flashcard_typed_answer": "",# The text the user typed for the current card
    "flashcard_known": set(),    # Set of card indices marked "I knew it"
    "flashcard_results": {},     # {card_index: True/False} — per-card grading
    "quiz": None,                # Result from Agent 3 generate
    "quiz_answers": {},          # {question_id: "A"|"B"|"C"|"D"}
    "quiz_result": None,         # Result from Agent 3 evaluate
    "detailed_notes": None,      # Result from generate_detailed_notes()
    "study_plan": None,          # Result from Agent 4
    "progress": None,            # Result from Agent 5
    "agent_status": {},          # {"name": "...", "status": "running"|"done"|"error"}
    "current_quiz_topic": "",    # Topic used for current quiz
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ── Orchestrator initialization (singleton) ───────────────────────────────────
if st.session_state["orchestrator"] is None:
    try:
        st.session_state["orchestrator"] = get_orchestrator()
    except Exception as e:
        st.error(f"⚠️ Configuration Error: {e}")
        st.info(
            "Please copy `.env.example` to `.env` and fill in your IBM Cloud credentials."
        )
        st.stop()

# ── Sidebar navigation ────────────────────────────────────────────────────────
pages = {
    "🏠 Home": "home",
    "📤 Upload Study Material": "upload",
    "📖 AI Study Notes": "notes",
    "🃏 Flashcards": "flashcards",
    "✏️ Practice Quiz": "quiz",
    "📅 Study Planner": "planner",
    "📊 Progress Dashboard": "progress",
}

st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/5/51/IBM_logo.svg",
    width=80,
)
st.sidebar.title("Smart Study Generator")
st.sidebar.markdown("*Powered by IBM Granite*")
st.sidebar.markdown("---")

selected = st.sidebar.radio("Navigation", list(pages.keys()))
page = pages[selected]

# Sidebar status footer
st.sidebar.markdown("---")
uploaded_docs = st.session_state.get("uploaded_docs", [])
flashcards = st.session_state.get("flashcards", [])
st.sidebar.markdown(f"📄 **{len(uploaded_docs)}** document(s) loaded")
st.sidebar.markdown(f"🃏 **{len(flashcards)}** flashcard(s) ready")

quiz_result = st.session_state.get("quiz_result")
if quiz_result and quiz_result.get("agent_status") != "error":
    score = quiz_result.get("score", 0)
    st.sidebar.markdown(f"📊 Last score: **{score}%**")


# ── Helper ────────────────────────────────────────────────────────────────────
def show_agent_status(agent_name: str, status: str):
    if status == "running":
        st.info(f"🤖 {agent_name} is running...")
    elif status == "done":
        st.success(f"✅ {agent_name} completed successfully")
    elif status == "error":
        st.error(f"❌ {agent_name} encountered an error")


# ── Page routing ──────────────────────────────────────────────────────────────
if page == "home":
    render_home()
elif page == "upload":
    render_upload()
elif page == "notes":
    render_notes()
elif page == "flashcards":
    render_flashcards()
elif page == "quiz":
    render_quiz()
elif page == "planner":
    render_study_planner()
elif page == "progress":
    render_progress()
