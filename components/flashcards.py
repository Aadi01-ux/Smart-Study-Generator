import random
import streamlit as st


# ── Answer comparison helper ──────────────────────────────────────────────────

def _score_answer(user_answer: str, correct_answer: str) -> float:
    """Return a similarity score in [0.0, 1.0] between the two strings.

    Uses token-overlap (Jaccard index on lowercase word sets).  No external
    libraries required.  A score of 1.0 means a perfect token overlap; 0.0
    means no words in common.
    """
    def tokens(text: str) -> set:
        # Lowercase, strip punctuation-only tokens
        return {
            w.strip(".,!?;:\"'()-") for w in text.lower().split()
            if w.strip(".,!?;:\"'()-")
        }

    user_tokens = tokens(user_answer)
    correct_tokens = tokens(correct_answer)
    if not correct_tokens:
        return 1.0  # edge-case: empty correct answer
    if not user_tokens:
        return 0.0
    intersection = user_tokens & correct_tokens
    union = user_tokens | correct_tokens
    return len(intersection) / len(union)  # Jaccard similarity


# ── Card state helper ─────────────────────────────────────────────────────────

def _reset_card_state(new_index: int) -> None:
    """Switch to a new card index and reset all per-card interactive state."""
    st.session_state["flashcard_index"] = new_index
    st.session_state["show_answer"] = False
    st.session_state["flashcard_submitted"] = False
    st.session_state["flashcard_typed_answer"] = ""


def render_flashcards():
    st.title("🃏 Flashcards")
    st.markdown("Review key concepts one card at a time and track what you know.")

    flashcards = st.session_state.get("flashcards", [])

    if not flashcards:
        st.info(
            "No flashcards yet. "
            "Go to the **AI Study Notes** page, enter a topic, and click **Generate Study Notes** "
            "to create flashcards from your uploaded document."
        )
        return

    total = len(flashcards)

    # ── Ensure all required state keys exist ──────────────────────────────────
    if "flashcard_index" not in st.session_state:
        st.session_state["flashcard_index"] = 0
    if "show_answer" not in st.session_state:
        st.session_state["show_answer"] = False
    # Whether the user has submitted their typed answer for this card
    if "flashcard_submitted" not in st.session_state:
        st.session_state["flashcard_submitted"] = False
    # The text the user typed for this card
    if "flashcard_typed_answer" not in st.session_state:
        st.session_state["flashcard_typed_answer"] = ""
    # Set of card indices the user marked as "I knew it"
    if "flashcard_known" not in st.session_state:
        st.session_state["flashcard_known"] = set()
    # Per-card grading log: {index: True/False}
    if "flashcard_results" not in st.session_state:
        st.session_state["flashcard_results"] = {}

    # Clamp index to valid range
    index = max(0, min(st.session_state["flashcard_index"], total - 1))
    st.session_state["flashcard_index"] = index

    card = flashcards[index]
    question = card.get("question", "")
    answer = card.get("answer", "")

    # ── Score summary bar ──────────────────────────────────────────────────────
    known_count = len(st.session_state["flashcard_known"])
    answered_count = len(st.session_state["flashcard_results"])
    unknown_count = answered_count - known_count

    col_score1, col_score2, col_score3, col_shuffle = st.columns([1, 1, 1, 1])
    with col_score1:
        st.metric("✅ Knew it", known_count)
    with col_score2:
        st.metric("❌ Didn't know", unknown_count)
    with col_score3:
        st.metric("📋 Remaining", total - answered_count)
    with col_shuffle:
        if st.button("🔀 Shuffle & Restart"):
            shuffled = flashcards[:]
            random.shuffle(shuffled)
            st.session_state["flashcards"] = shuffled
            st.session_state["flashcard_index"] = 0
            st.session_state["show_answer"] = False
            st.session_state["flashcard_known"] = set()
            st.session_state["flashcard_results"] = {}
            st.rerun()

    # ── Progress bar ──────────────────────────────────────────────────────────
    st.progress((index + 1) / total)
    st.caption(f"Card **{index + 1}** of **{total}**")

    # ── Question card ─────────────────────────────────────────────────────────
    st.markdown("---")

    already_answered = index in st.session_state["flashcard_results"]
    submitted = st.session_state.get("flashcard_submitted", False)

    # Card header reflects grading status when already answered
    if already_answered:
        was_known = st.session_state["flashcard_results"][index]
        card_title = "✅ Question (Correct)" if was_known else "❌ Question (Incorrect)"
    else:
        card_title = "❓ Question"

    with st.container(border=True):
        st.subheader(card_title)
        st.markdown(f"**{question}**")

    # ── Answer input phase (before submission) ────────────────────────────────
    if not submitted:
        # Use on_change callback to sync typed text into session_state reliably.
        # The text_area value is driven by the session_state key directly.
        typed = st.text_area(
            "✏️ Type your answer:",
            value=st.session_state.get("flashcard_typed_answer", ""),
            height=100,
            placeholder="Write your answer here before revealing the correct one…",
            key=f"fc_input_{index}",  # unique key per card prevents stale widget state
        )
        # Mirror the widget value back into session_state on every render
        st.session_state["flashcard_typed_answer"] = typed

        if st.button(
            "📩 Submit Answer",
            type="primary",
            use_container_width=True,
            disabled=not typed.strip(),
        ):
            st.session_state["flashcard_submitted"] = True
            st.rerun()

    else:
        # ── Feedback phase (after submission) ────────────────────────────────
        typed = st.session_state.get("flashcard_typed_answer", "")

        # Show what the user wrote
        with st.container(border=True):
            st.subheader("📝 Your Answer")
            st.markdown(typed if typed.strip() else "_No answer entered._")

        # Show the correct answer
        with st.container(border=True):
            st.subheader("💡 Correct Answer")
            st.success(answer)

        # Fuzzy comparison
        score = _score_answer(typed, answer)
        if score >= 0.5:
            feedback_icon = "✅"
            feedback_msg = (
                f"**Good match!** Your answer covers the key points "
                f"({round(score * 100)}% word overlap)."
            )
            auto_result = True
        elif score >= 0.2:
            feedback_icon = "🟡"
            feedback_msg = (
                f"**Partial match.** You got some of it right "
                f"({round(score * 100)}% word overlap). Check the correct answer above."
            )
            auto_result = False
        else:
            feedback_icon = "❌"
            feedback_msg = (
                f"**Low match** ({round(score * 100)}% word overlap). "
                "Review the correct answer and try to understand why."
            )
            auto_result = False

        st.markdown(f"{feedback_icon} {feedback_msg}")

        # ── Grade this card (override available) ─────────────────────────────
        if not already_answered:
            st.markdown("**Confirm your result:**")
            col_knew, col_didnt = st.columns(2)
            with col_knew:
                # Pre-select the button matching the auto result
                btn_type_knew = "primary" if auto_result else "secondary"
                if st.button(
                    "✅ I knew it",
                    type=btn_type_knew,
                    use_container_width=True,
                ):
                    st.session_state["flashcard_results"][index] = True
                    st.session_state["flashcard_known"].add(index)
                    if index < total - 1:
                        _reset_card_state(index + 1)
                    st.rerun()
            with col_didnt:
                btn_type_didnt = "primary" if not auto_result else "secondary"
                if st.button(
                    "❌ I didn't know it",
                    type=btn_type_didnt,
                    use_container_width=True,
                ):
                    st.session_state["flashcard_results"][index] = False
                    if index < total - 1:
                        _reset_card_state(index + 1)
                    st.rerun()
        else:
            # Already graded on a previous visit — show recorded result
            was_known = st.session_state["flashcard_results"][index]
            if was_known:
                st.success("✅ You marked this card as **correct**.")
            else:
                st.warning("❌ You marked this card as **incorrect**. Review it again!")

        # Explicit "Next Card" button (always available after submission)
        if index < total - 1:
            if st.button("▶️ Next Card", type="primary", use_container_width=True):
                _reset_card_state(index + 1)
                st.rerun()
        else:
            st.info("🏁 This is the last card. Use the navigation below or restart.")

        # Try again button — lets the user re-type their answer for this card
        if st.button("🔄 Try Again", use_container_width=True):
            st.session_state["flashcard_submitted"] = False
            st.session_state["flashcard_typed_answer"] = ""
            st.rerun()

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("---")
    col_prev, col_spacer, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← Previous", disabled=(index == 0), use_container_width=True):
            _reset_card_state(index - 1)
            st.rerun()
    with col_next:
        if st.button("Next →", disabled=(index == total - 1), use_container_width=True):
            _reset_card_state(index + 1)
            st.rerun()

    # ── Session summary (shown when all cards have been answered) ─────────────
    if answered_count == total:
        st.markdown("---")
        st.subheader("🏆 Session Complete!")
        pct = round((known_count / total) * 100)
        st.metric("Your score", f"{known_count} / {total}  ({pct}%)")

        if pct == 100:
            st.success("🎉 Perfect! You knew all the flashcards.")
        elif pct >= 70:
            st.success(f"👍 Good work! You knew {known_count} out of {total} cards.")
        else:
            st.warning(
                f"📚 You knew {known_count} out of {total} cards. "
                "Review the ones you missed and try again."
            )

        # List cards that were not known
        missed = [
            flashcards[i]
            for i in range(total)
            if not st.session_state["flashcard_results"].get(i, True)
        ]
        if missed:
            with st.expander(f"📋 {len(missed)} card(s) to review again"):
                for i, card in enumerate(missed, 1):
                    st.markdown(f"**{i}. {card.get('question', '')}**")
                    st.info(card.get("answer", ""))

        col_restart, col_missed_only = st.columns(2)
        with col_restart:
            if st.button("🔁 Restart All Cards", use_container_width=True):
                st.session_state["flashcard_index"] = 0
                st.session_state["show_answer"] = False
                st.session_state["flashcard_known"] = set()
                st.session_state["flashcard_results"] = {}
                st.rerun()
        with col_missed_only:
            if missed and st.button("🎯 Practice Missed Cards Only", use_container_width=True):
                st.session_state["flashcards"] = missed
                st.session_state["flashcard_index"] = 0
                st.session_state["show_answer"] = False
                st.session_state["flashcard_known"] = set()
                st.session_state["flashcard_results"] = {}
                st.rerun()
