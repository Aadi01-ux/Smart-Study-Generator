import streamlit as st

# ---------------------------------------------------------------------------
# Shared rate-limit helper
# ---------------------------------------------------------------------------

_RATE_LIMIT_MSG = (
    "IBM watsonx.ai free usage limit reached. "
    "Please wait a few minutes and try again later."
)


def _is_rate_limited(result: dict) -> bool:
    """Return True when *result* carries the rate_limit status."""
    return result.get("agent_status") == "rate_limit"


def _show_rate_limit_warning() -> None:
    """Render the standard rate-limit warning banner in the current page."""
    st.warning(
        "⏳ **IBM watsonx.ai free usage limit reached.**  \n"
        "The model is temporarily unavailable on your free plan.  \n"
        "Please wait a few minutes and try again.",
        icon="🚫",
    )


def render_home():
    st.title("📚 Smart Study Generator Agent")
    st.subheader("Powered by IBM Granite 4H Small | Multi-Agent AI System")
    st.markdown("---")

    st.header("🤖 Agent Overview")
    st.markdown(
        """
| Agent | Responsibility | Output |
|---|---|---|
| 🔍 Resource Analyzer | Reads PDFs/TXT, extracts topics and definitions | Subject, topics, key concepts |
| 📝 Study Material Generator | Creates notes, summaries, flashcards | Student-friendly study material |
| ✏️ Assessment Agent | Generates MCQ quizzes, evaluates answers | Quiz questions, scores, weak topics |
| 📅 Study Planner | Creates personalized daily study schedule | Daily timetable |
| 📊 Progress & Recommendation | Analyzes performance, recommends next steps | Progress report, recommendations |
"""
    )

    st.header("🚀 Quick Start Guide")
    st.markdown(
        """
1. **Upload** your PDF or TXT study material on the **Upload Study Material** page.
2. **Generate Notes** by visiting the **AI Study Notes** page and entering a topic.
3. **Review Flashcards** on the **Flashcards** page for quick memory checks.
4. **Test Yourself** on the **Practice Quiz** page — get scored with detailed feedback.
5. **Plan Your Study** on the **Study Planner** page to create a personalised schedule.
6. **Track Progress** on the **Progress Dashboard** to see your improvement over time.
"""
    )

    st.info("👉 Get started by uploading your study material on the **Upload Study Material** page.")

    # Show summary of what's loaded in this session
    st.markdown("---")
    st.header("📋 Current Session Summary")
    col1, col2, col3 = st.columns(3)
    with col1:
        docs = st.session_state.get("uploaded_docs", [])
        st.metric("Documents Uploaded", len(docs))
    with col2:
        flashcards = st.session_state.get("flashcards", [])
        st.metric("Flashcards Available", len(flashcards))
    with col3:
        quiz_result = st.session_state.get("quiz_result")
        score = quiz_result.get("score", 0) if quiz_result else 0
        st.metric("Last Quiz Score", f"{score}%" if quiz_result else "—")


def _reset_flashcard_state() -> None:
    """Clear all flashcard interaction state (called when a new deck is stored)."""
    st.session_state["flashcard_index"] = 0
    st.session_state["show_answer"] = False
    st.session_state["flashcard_submitted"] = False
    st.session_state["flashcard_typed_answer"] = ""
    st.session_state["flashcard_known"] = set()
    st.session_state["flashcard_results"] = {}


def render_notes():
    st.title("📖 AI Study Notes")

    orchestrator = st.session_state.get("orchestrator")
    if orchestrator is None:
        st.warning("Please configure the application first.")
        return

    # ── Document status ───────────────────────────────────────────────────────
    uploaded_docs = orchestrator.list_uploaded_documents()
    if not uploaded_docs:
        st.warning(
            "⚠️ No documents are indexed yet. "
            "Upload a PDF or TXT on the **Upload Study Material** page first."
        )
        return

    doc_names = [d.get("filename", "?") for d in uploaded_docs]
    st.info(f"📄 **{len(uploaded_docs)} document(s) indexed:** {', '.join(doc_names)}")

    # ── Two-tab layout ────────────────────────────────────────────────────────
    tab_quick, tab_detailed = st.tabs(
        ["🔍 Quick Topic Notes", "📚 Detailed Exam Notes (Full Document)"]
    )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — Quick topic-focused notes (existing behaviour, unchanged)
    # ══════════════════════════════════════════════════════════════════════════
    with tab_quick:
        st.markdown(
            "Enter a topic or question. The AI retrieves the most relevant "
            "passages from your document and generates focused study notes."
        )

        study_material = st.session_state.get("study_material")
        if study_material and not study_material.get("error"):
            st.success("✅ Quick notes are available below.")

        query = st.text_input(
            "Enter a topic or question:",
            key="notes_query",
            placeholder="e.g. What is machine learning?",
        )

        if st.button("Generate Quick Notes", type="primary", disabled=not query.strip()):
            with st.spinner("🤖 Study Material Generator is running..."):
                result = orchestrator.generate_study_material(
                    query, st.session_state.get("analysis")
                )
            if _is_rate_limited(result):
                _show_rate_limit_warning()
            elif result.get("agent_status") == "error":
                st.error(f"❌ {result.get('error', 'Unknown error')}")
            else:
                st.session_state["study_material"] = result
                new_flashcards = result.get("flashcards", [])
                if new_flashcards != st.session_state.get("flashcards", []):
                    _reset_flashcard_state()
                st.session_state["flashcards"] = new_flashcards
                if result.get("error"):
                    st.warning(f"⚠️ Notes generated with limited quality. Details: {result['error']}")
                else:
                    st.success("✅ Study Material Generator completed successfully")

        material = st.session_state.get("study_material")
        if material and material.get("agent_status") != "error":
            st.markdown("---")
            if material.get("error"):
                with st.expander("⚠️ Generation issue", expanded=False):
                    st.warning(material["error"])

            summary = material.get("summary", "")
            if summary and "Notes generation failed" not in summary:
                with st.expander("📄 Summary", expanded=True):
                    st.write(summary)

            notes = material.get("notes", [])
            if notes:
                st.subheader("📝 Study Notes")
                for note in notes:
                    st.markdown(f"• {note}")

            simplified = material.get("simplified_concepts", [])
            if simplified:
                st.subheader("💡 Simplified Concepts")
                for concept in simplified:
                    title = concept.get("concept", concept) if isinstance(concept, dict) else str(concept)
                    explanation = concept.get("explanation", "") if isinstance(concept, dict) else ""
                    with st.expander(title):
                        if explanation:
                            st.write(explanation)

            flashcards = st.session_state.get("flashcards", [])
            if flashcards:
                st.info(
                    f"🃏 {len(flashcards)} flashcard(s) generated! "
                    "Go to the **Flashcards** page to review them."
                )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — Detailed full-document exam notes
    # ══════════════════════════════════════════════════════════════════════════
    with tab_detailed:
        st.markdown(
            "Generates **comprehensive, topic-wise exam notes** for the entire uploaded "
            "document. Every section of the PDF is processed in order — nothing is skipped. "
            "This may take a minute for longer documents."
        )

        # Document selector (if multiple docs are uploaded)
        if len(uploaded_docs) == 1:
            selected_doc = uploaded_docs[0]
        else:
            filenames = [d.get("filename", "?") for d in uploaded_docs]
            chosen_name = st.selectbox("Select document to generate notes for:", filenames)
            selected_doc = next(
                (d for d in uploaded_docs if d.get("filename") == chosen_name),
                uploaded_docs[0],
            )

        sel_doc_id = selected_doc.get("doc_id", "")
        sel_filename = selected_doc.get("filename", "unknown")

        # Show previously generated detailed notes for this document
        detailed = st.session_state.get("detailed_notes")
        notes_for_this_doc = (
            detailed is not None
            and detailed.get("filename") == sel_filename
            and detailed.get("agent_status") != "error"
        )

        if notes_for_this_doc:
            st.success(
                f"✅ Detailed notes for **{sel_filename}** are ready "
                f"({detailed.get('total_batches', '?')} sections processed)."
            )

        if st.button(
            "📚 Generate Detailed Exam Notes",
            type="primary",
            use_container_width=True,
            key="btn_detailed_notes",
        ):
            st.session_state["detailed_notes"] = None  # clear stale result

            # ── Live progress display ────────────────────────────────────────
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            def _on_progress(batch_num: int, total_batches: int, hint: str) -> None:
                pct = (batch_num - 1) / max(total_batches, 1)
                progress_bar.progress(pct)
                label = f"🤖 Processing section {batch_num} of {total_batches}"
                if hint:
                    label += f" — *{hint[:60]}…*"
                status_text.markdown(label)

            result = orchestrator.generate_detailed_notes(
                sel_doc_id, sel_filename, progress_callback=_on_progress
            )

            progress_bar.progress(1.0)

            if _is_rate_limited(result):
                status_text.markdown("⏳ Rate limit reached.")
                _show_rate_limit_warning()
            elif result.get("agent_status") == "error":
                status_text.markdown("❌ Generation failed.")
                st.error(f"Error: {result.get('error', 'Unknown error')}")
            elif result.get("error"):
                status_text.markdown("⚠️ Completed with issues.")
                st.warning(result["error"])
                st.session_state["detailed_notes"] = result
            else:
                sections = result.get("sections", [])
                stats = result.get("coverage_stats", {})
                status_text.markdown(
                    f"✅ Complete — **{len(sections)} section(s)** generated "
                    f"covering the entire document."
                )
                st.session_state["detailed_notes"] = result
                # ── Coverage status ──────────────────────────────────────────
                if stats:
                    st.markdown("#### 📊 Coverage Status")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Outline Topics", stats.get("outline_topics", "—"))
                    c2.metric("Sections Generated", stats.get("generated_sections", "—"))
                    c3.metric("Subheadings Generated", stats.get("generated_subheadings", "—"))
                    cov = stats.get("coverage_pct", None)
                    c4.metric("Coverage", f"{cov}%" if cov is not None else "—")
                    missing = stats.get("missing_sections", [])
                    if missing:
                        with st.expander(
                            f"⚠️ {len(missing)} outline topic(s) may need review", expanded=False
                        ):
                            for m in missing:
                                st.markdown(f"- {m}")

        # ── Display detailed notes ────────────────────────────────────────────
        detailed = st.session_state.get("detailed_notes")
        if (
            detailed
            and detailed.get("agent_status") != "error"
            and detailed.get("filename") == sel_filename
            and detailed.get("sections")
        ):
            sections = detailed["sections"]
            toc = detailed.get("toc", [])
            full_md = detailed.get("full_markdown", "")

            st.markdown("---")

            # Table of contents
            with st.expander("📋 Table of Contents", expanded=True):
                for i, heading in enumerate(toc, 1):
                    st.markdown(f"{i}. {heading}")

            st.markdown("---")

            # One expandable section per Granite batch
            for i, section in enumerate(sections):
                heading = section.get("heading", f"Section {i + 1}")
                content = section.get("content", "")
                expanded = (i == 0)  # first section open by default
                with st.expander(f"**{i + 1}. {heading}**", expanded=expanded):
                    st.markdown(content)

            # Download button
            st.markdown("---")
            if full_md:
                st.download_button(
                    label="⬇️ Download Notes as Markdown (.md)",
                    data=full_md.encode("utf-8"),
                    file_name=f"exam_notes_{sel_filename.replace(' ', '_')}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
                st.download_button(
                    label="⬇️ Download Notes as Plain Text (.txt)",
                    data=full_md.encode("utf-8"),
                    file_name=f"exam_notes_{sel_filename.replace(' ', '_')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )


def render_progress():
    st.title("📊 Progress Dashboard")
    st.markdown("Track your learning performance across all quizzes and topics.")

    orchestrator = st.session_state.get("orchestrator")
    if orchestrator is None:
        st.warning("Please configure the application first.")
        return

    if st.button("🔄 Refresh Progress Report", type="primary"):
        with st.spinner("🤖 Progress & Recommendation Agent is analyzing your performance..."):
            result = orchestrator.get_progress_report()
        if _is_rate_limited(result):
            _show_rate_limit_warning()
        elif result.get("agent_status") == "error":
            st.error(f"❌ {result.get('error', 'Unknown error')}")
        else:
            st.session_state["progress"] = result
            st.success("✅ Progress & Recommendation Agent completed successfully")

    progress = st.session_state.get("progress")
    if not progress:
        st.info("No progress data yet. Complete a quiz to see your progress here.")
        return

    st.markdown("---")

    # Strong vs Weak topics
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("💪 Strong Topics")
        strong = progress.get("strong_topics", [])
        if strong:
            for topic in strong:
                st.success(f"✅ {topic}")
        else:
            st.info("No strong topics identified yet.")

    with col2:
        st.subheader("⚠️ Weak Topics")
        weak = progress.get("weak_topics", [])
        if weak:
            for topic in weak:
                st.warning(f"⚠️ {topic}")
        else:
            st.info("No weak topics identified — great work!")

    st.markdown("---")

    # Score history chart
    st.subheader("📈 Score History")
    try:
        from services.storage_service import get_storage_service
        storage = get_storage_service()
        quiz_results = storage.load_quiz_results()
        if quiz_results:
            scores = []
            labels = []
            for i, qr in enumerate(quiz_results):
                score_val = qr.get("score", 0)
                scores.append(score_val)
                ts = qr.get("timestamp", f"Quiz {i + 1}")
                labels.append(str(ts)[:10] if len(str(ts)) > 10 else str(ts))
            import pandas as pd
            chart_data = pd.DataFrame({"Score (%)": scores}, index=labels)
            st.line_chart(chart_data)
        else:
            st.info("No quiz history yet.")
    except Exception as e:
        st.info(f"Score history unavailable: {e}")

    # Milestones
    milestones = progress.get("milestones", [])
    if milestones:
        st.subheader("🏆 Milestones")
        for milestone in milestones:
            st.markdown(f"✔️ {milestone}")

    # Recommendations
    recommendations = progress.get("recommendations", [])
    if recommendations:
        st.subheader("💡 Recommendations")
        for i, rec in enumerate(recommendations, 1):
            st.markdown(f"{i}. {rec}")

    # Next topic
    next_topic = progress.get("next_topic", "")
    if next_topic:
        st.markdown("---")
        st.subheader("🎯 Recommended Next Topic")
        st.info(f"**{next_topic}**")
