import datetime
import streamlit as st
from components.dashboard import _is_rate_limited, _show_rate_limit_warning


def render_study_planner():
    st.title("📅 Study Planner")
    st.markdown(
        "Generate a personalised daily study schedule tailored to your exam date and topics."
    )

    orchestrator = st.session_state.get("orchestrator")
    if orchestrator is None:
        st.warning("Please configure the application first.")
        return

    # Pre-populate weak topics hint from progress
    progress = st.session_state.get("progress")
    weak_topics_hint = ""
    if progress:
        weak = progress.get("weak_topics", [])
        if weak:
            st.info(f"⚠️ Weak topics from your quiz history: **{', '.join(weak)}**")
            weak_topics_hint = "\n".join(weak)

    # ── Plan Generation Form ─────────────────────────────────────────────────
    st.subheader("📋 Create Your Study Plan")

    with st.form("study_plan_form"):
        subject = st.text_input(
            "Subject name",
            placeholder="e.g. Biology, Computer Science, History",
        )

        exam_date = st.date_input(
            "Exam date",
            min_value=datetime.date.today(),
            value=datetime.date.today() + datetime.timedelta(days=14),
        )

        hours_per_day = st.number_input(
            "Hours available per day",
            min_value=0.5,
            max_value=12.0,
            value=2.0,
            step=0.5,
        )

        topics_text = st.text_area(
            "Topics to cover (one per line)",
            value=weak_topics_hint,
            placeholder="e.g.\nCell Biology\nGenetics\nEvolution",
            height=150,
        )

        submitted = st.form_submit_button("📅 Generate Study Plan", type="primary")

    if submitted:
        if not subject.strip():
            st.error("Please enter a subject name.")
            return

        topics_list = [t.strip() for t in topics_text.split("\n") if t.strip()]
        if not topics_list:
            st.error("Please enter at least one topic to cover.")
            return

        exam_date_str = exam_date.strftime("%Y-%m-%d")

        with st.spinner("🤖 Study Planner Agent is generating your schedule..."):
            result = orchestrator.generate_study_plan(
                subject.strip(),
                exam_date_str,
                hours_per_day,
                topics_list,
            )

        if _is_rate_limited(result):
            _show_rate_limit_warning()
        elif result.get("agent_status") == "error":
            st.error(f"❌ {result.get('error', 'Unknown error')}")
        else:
            st.session_state["study_plan"] = result
            st.success("✅ Study Planner Agent completed successfully!")

    # ── Display Plan ──────────────────────────────────────────────────────────
    plan = st.session_state.get("study_plan")
    if plan and plan.get("agent_status") != "error":
        st.markdown("---")
        st.subheader("📆 Your Study Plan")

        # Summary row
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Subject", plan.get("subject", "—"))
        with col2:
            st.metric("Exam Date", plan.get("exam_date", "—"))
        with col3:
            total_days = plan.get("total_days", len(plan.get("daily_plan", [])))
            st.metric("Total Days", total_days)

        # Daily plan table
        daily_plan = plan.get("daily_plan", [])
        if daily_plan:
            import pandas as pd

            rows = []
            for entry in daily_plan:
                rows.append(
                    {
                        "Day": entry.get("day", ""),
                        "Date": entry.get("date", ""),
                        "Topics": entry.get("topic", entry.get("topics", "")),
                        "Hours": entry.get("hours", ""),
                        "Activities": entry.get("activities", ""),
                        "Priority": entry.get("priority", ""),
                    }
                )
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No daily plan data returned.")

        # Study tips
        tips = plan.get("study_tips", [])
        if tips:
            st.subheader("💡 Study Tips")
            for tip in tips:
                st.markdown(f"• {tip}")
