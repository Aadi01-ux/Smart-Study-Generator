import streamlit as st
from components.dashboard import _is_rate_limited, _show_rate_limit_warning


def render_quiz():
    st.title("✏️ Practice Quiz")
    st.markdown("Test your knowledge with AI-generated multiple-choice questions.")

    orchestrator = st.session_state.get("orchestrator")
    if orchestrator is None:
        st.warning("Please configure the application first.")
        return

    # ── Quiz Generation ─────────────────────────────────────────────────────
    st.subheader("🎯 Generate a New Quiz")

    topic = st.text_input(
        "Enter topic for quiz:",
        key="quiz_topic_input",
        placeholder="e.g. Photosynthesis, World War II, Python loops",
    )

    if st.button("Generate Quiz", type="primary", disabled=not topic.strip()):
        with st.spinner("🤖 Assessment Agent is generating questions..."):
            result = orchestrator.generate_quiz(topic.strip())
        if _is_rate_limited(result):
            _show_rate_limit_warning()
        elif result.get("agent_status") == "error":
            st.error(f"❌ {result.get('error', 'Unknown error')}")
        else:
            st.session_state["quiz"] = result
            st.session_state["quiz_answers"] = {}
            st.session_state["quiz_result"] = None
            st.session_state["current_quiz_topic"] = topic.strip()
            st.success("✅ Quiz generated! Answer the questions below.")
            st.rerun()

    quiz = st.session_state.get("quiz")

    # ── Quiz Display ─────────────────────────────────────────────────────────
    if quiz and quiz.get("agent_status") != "error":
        questions = quiz.get("questions", [])
        current_topic = st.session_state.get("current_quiz_topic", "")

        st.markdown("---")
        st.subheader(f"📝 Quiz: {current_topic}")
        st.markdown(f"**{len(questions)} question(s)**")

        quiz_answers = st.session_state.get("quiz_answers", {})

        for i, q in enumerate(questions):
            q_id = q.get("id", str(i))
            q_text = q.get("question", q.get("text", f"Question {i + 1}"))
            options = q.get("options", {})

            st.markdown(f"**{i + 1}. {q_text}**")

            # Build radio choices in A/B/C/D order
            choices = []
            for letter in ["A", "B", "C", "D"]:
                if letter in options:
                    choices.append(f"{letter}: {options[letter]}")

            if not choices:
                # Fallback: options may be a list
                if isinstance(options, list):
                    for j, opt in enumerate(options):
                        letter = chr(65 + j)  # A, B, C, D
                        choices.append(f"{letter}: {opt}")

            current_val = quiz_answers.get(q_id)
            # Find index of current selection in choices
            default_idx = None
            if current_val:
                for idx, ch in enumerate(choices):
                    if ch.startswith(current_val + ":") or ch == current_val:
                        default_idx = idx
                        break

            selected = st.radio(
                f"q_{q_id}",
                choices,
                index=default_idx,
                key=f"radio_{q_id}",
                label_visibility="collapsed",
            )

            if selected:
                letter = selected.split(":")[0].strip()
                quiz_answers[q_id] = letter

        st.session_state["quiz_answers"] = quiz_answers

        # Check if all questions are answered
        all_answered = all(
            st.session_state["quiz_answers"].get(q.get("id", str(i))) is not None
            for i, q in enumerate(questions)
        )

        st.markdown("---")
        if not all_answered:
            st.warning("Please answer all questions before submitting.")

        if st.button("Submit Quiz ✅", type="primary", disabled=not all_answered):
            answers_list = [
                st.session_state["quiz_answers"].get(q.get("id", str(i)))
                for i, q in enumerate(questions)
            ]
            with st.spinner("Evaluating your answers..."):
                result = orchestrator.evaluate_quiz(questions, answers_list)
            if _is_rate_limited(result):
                _show_rate_limit_warning()
            elif result.get("agent_status") == "error":
                st.error(f"❌ {result.get('error', 'Unknown error')}")
            else:
                st.session_state["quiz_result"] = result
                st.success("✅ Quiz evaluated!")
                st.rerun()

    # ── Results Display ───────────────────────────────────────────────────────
    quiz_result = st.session_state.get("quiz_result")
    if quiz_result and quiz_result.get("agent_status") != "error":
        st.markdown("---")
        st.subheader("🏆 Quiz Results")

        score = quiz_result.get("score", 0)
        col1, col2 = st.columns([1, 3])
        with col1:
            st.metric("Score", f"{score}%")
        with col2:
            st.progress(int(score) / 100)

        # Per-question breakdown — join with original questions to get text
        per_question = quiz_result.get("per_question", [])
        orig_questions = (st.session_state.get("quiz") or {}).get("questions", [])
        q_text_by_id = {q.get("id", str(i)): q.get("question", f"Question {i+1}")
                        for i, q in enumerate(orig_questions)}

        if per_question:
            st.subheader("📋 Question Breakdown")
            for item in per_question:
                q_id = item.get("question_id", "")
                q_text = q_text_by_id.get(q_id, f"Question {q_id}")
                correct = item.get("correct", False)
                explanation = item.get("explanation", "")
                icon = "✅" if correct else "❌"
                with st.expander(f"{icon} Q{q_id}: {q_text}"):
                    if explanation:
                        st.write(explanation)
                    if not correct:
                        correct_answer = item.get("correct_answer", "")
                        student_answer = item.get("student_answer", "")
                        if correct_answer:
                            st.markdown(f"**Correct Answer:** {correct_answer}")
                        if student_answer:
                            st.markdown(f"**Your Answer:** {student_answer}")

        # Weak topics
        weak_topics = quiz_result.get("weak_topics", [])
        if weak_topics:
            st.warning("⚠️ Topics to review: " + ", ".join(weak_topics))

        # Reset button
        if st.button("🔁 Take Another Quiz"):
            st.session_state["quiz"] = None
            st.session_state["quiz_answers"] = {}
            st.session_state["quiz_result"] = None
            st.session_state["current_quiz_topic"] = ""
            st.rerun()
