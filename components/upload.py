import streamlit as st
from components.dashboard import _is_rate_limited, _show_rate_limit_warning


def render_upload():
    st.title("📤 Upload Study Material")
    st.markdown(
        "Upload your PDF or TXT study files. "
        "Each file will be analyzed by the **Resource Analyzer Agent** and stored for future use."
    )

    orchestrator = st.session_state.get("orchestrator")
    if orchestrator is None:
        st.warning("Please configure the application first.")
        return

    # Show currently stored documents
    st.subheader("📚 Documents in Knowledge Base")
    try:
        stored_docs = orchestrator.list_uploaded_documents()
        st.session_state["uploaded_docs"] = stored_docs
    except Exception:
        stored_docs = st.session_state.get("uploaded_docs", [])

    if stored_docs:
        st.success(f"{len(stored_docs)} document(s) currently stored:")
        for doc in stored_docs:
            st.markdown(f"• 📄 **{doc.get('filename', doc.get('doc_id', 'Unknown'))}**")
    else:
        st.info("No documents uploaded yet. Upload files below to get started.")

    st.markdown("---")
    st.subheader("📂 Upload New Files")

    uploaded_files = st.file_uploader(
        "Upload PDF or TXT files",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        key="file_uploader",
    )

    if uploaded_files:
        st.markdown(f"**{len(uploaded_files)} file(s) selected.**")

    if st.button("🔍 Analyze Documents", type="primary", disabled=not uploaded_files):
        latest_analysis = None
        any_success = False

        for uploaded_file in uploaded_files:
            with st.spinner(
                f"🤖 Resource Analyzer Agent is processing **{uploaded_file.name}**..."
            ):
                file_bytes = uploaded_file.read()
                result = orchestrator.process_document(file_bytes, uploaded_file.name)

            if _is_rate_limited(result):
                _show_rate_limit_warning()
                break  # stop processing further files; limit is account-wide
            elif result.get("agent_status") == "error":
                st.error(f"❌ **{uploaded_file.name}**: {result.get('error', 'Unknown error')}")
            elif result.get("skipped"):
                st.info(
                    f"ℹ️ **{uploaded_file.name}**: Already uploaded — duplicate skipped."
                )
            else:
                st.success(f"✅ **{uploaded_file.name}**: Analyzed successfully.")
                latest_analysis = result
                any_success = True

        # Store latest successful analysis and refresh doc list
        if latest_analysis:
            st.session_state["analysis"] = latest_analysis

        # Refresh stored documents list
        try:
            st.session_state["uploaded_docs"] = orchestrator.list_uploaded_documents()
        except Exception:
            pass

        if any_success:
            st.markdown("---")
            st.subheader("📋 Analysis Results")
            _show_analysis(latest_analysis)

    # Show analysis results from session if available
    elif st.session_state.get("analysis"):
        st.markdown("---")
        st.subheader("📋 Last Analysis Results")
        _show_analysis(st.session_state["analysis"])


def _show_analysis(result: dict):
    """Display the structured analysis output from Agent 1."""
    if not result or result.get("agent_status") == "error":
        if result:
            st.error(result.get("error", "Unknown error"))
        return

    subject = result.get("subject", "")
    if subject:
        st.markdown(f"**📖 Subject:** {subject}")

    topics = result.get("topics", [])
    if topics:
        st.markdown("**🗂️ Topics Identified:**")
        for topic in topics:
            st.markdown(f"  • {topic}")

    subtopics = result.get("subtopics", [])
    if subtopics:
        with st.expander("📌 Subtopics"):
            for st_item in subtopics:
                st.markdown(f"  • {st_item}")

    definitions = result.get("definitions", {})
    if definitions:
        with st.expander("📖 Key Definitions"):
            if isinstance(definitions, dict):
                for term, defn in definitions.items():
                    st.markdown(f"**{term}:** {defn}")
            elif isinstance(definitions, list):
                for item in definitions:
                    if isinstance(item, dict):
                        term = item.get("term", "")
                        defn = item.get("definition", "")
                        st.markdown(f"**{term}:** {defn}")
                    else:
                        st.markdown(f"• {item}")

    key_concepts = result.get("key_concepts", [])
    if key_concepts:
        with st.expander("💡 Key Concepts"):
            for concept in key_concepts:
                st.markdown(f"  • {concept}")
