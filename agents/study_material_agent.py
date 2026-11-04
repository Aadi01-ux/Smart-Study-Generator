"""Agent 2 — Study Material Agent.

Two modes of operation:
1. run()                  — quick topic-focused notes using ChromaDB similarity search.
2. generate_detailed_notes() — full-document exam notes via a two-stage pipeline:
       Stage 1: Extract a structured chapter/topic/subtopic OUTLINE from the PDF.
       Stage 2: Generate detailed notes for every outline item, one topic at a time.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an expert study material generator. Your only output is a single "
    "valid JSON object — no prose, no markdown, no code fences. "
    "Generate clear, concise, student-friendly study content."
)

# System prompt used for Stage 2 (per-topic detailed notes generation).
_NOTES_SYSTEM_PROMPT = (
    "You are an expert academic tutor writing detailed college exam notes. "
    "Your output is structured Markdown only — no JSON, no code fences. "
    "Every subtopic must have its own heading and a full explanation paragraph."
)

# Stage 1: extract outline as JSON.
_OUTLINE_SYSTEM_PROMPT = (
    "You are an expert academic document analyst. "
    "Your only output is a single valid JSON object — no prose, no markdown, no code fences."
)

# Characters of document text sent to Stage 1 for outline extraction.
# Using the first 6000 chars gives Granite a broad view of the document structure.
_OUTLINE_CHARS = 6000

# How many ChromaDB chunks are retrieved per topic during Stage 2.
# More chunks = more source context = better coverage of each topic.
_CHUNKS_PER_TOPIC = 6

# Maximum characters of retrieved context passed to Granite per topic call.
# ~4000 chars (~600-800 words) leaves ample room in the context window for
# a 2000-token detailed output without truncation.
_MAX_CONTEXT_CHARS = 4000

# Output token budget per topic generation call.
_TOPIC_MAX_TOKENS = 2000

# Defaults used when Granite omits a key in the quick-notes path
_KEY_DEFAULTS: dict = {
    "notes": [],
    "summary": "",
    "flashcards": [],
    "simplified_concepts": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_outline(raw: dict) -> list[dict]:
    """Normalise the outline JSON returned by Stage 1 into a flat list of
    ``{"chapter": str, "topic": str, "subtopics": [str]}`` dicts.

    Accepts several possible shapes Granite might return:
    - {"chapters": [{"title": ..., "topics": [...]}]}
    - {"outline": [{"chapter": ..., "topics": [...]}]}
    - {"topics": ["...", ...]}   (flat list fallback)
    """
    if not isinstance(raw, dict):
        return []

    # Shape 1: {"chapters": [...]}
    chapters = raw.get("chapters") or raw.get("outline") or []
    if isinstance(chapters, list) and chapters:
        result = []
        for ch_idx, ch in enumerate(chapters):
            if not isinstance(ch, dict):
                continue
            ch_title = (
                ch.get("title") or ch.get("chapter") or ch.get("name")
                or f"Chapter {ch_idx + 1}"
            )
            topics = ch.get("topics") or ch.get("sections") or []
            if not isinstance(topics, list):
                topics = []
            if not topics:
                # chapter with no sub-topics: treat chapter itself as one topic
                result.append({
                    "chapter": ch_title,
                    "topic": ch_title,
                    "subtopics": ch.get("subtopics") or [],
                })
            else:
                for t_idx, t in enumerate(topics):
                    if isinstance(t, str):
                        result.append({
                            "chapter": ch_title,
                            "topic": t,
                            "subtopics": [],
                        })
                    elif isinstance(t, dict):
                        t_title = (
                            t.get("title") or t.get("topic") or t.get("name")
                            or f"Topic {t_idx + 1}"
                        )
                        subs = t.get("subtopics") or t.get("sections") or []
                        if not isinstance(subs, list):
                            subs = []
                        result.append({
                            "chapter": ch_title,
                            "topic": t_title,
                            "subtopics": [
                                s if isinstance(s, str) else str(s)
                                for s in subs
                            ],
                        })
        if result:
            return result

    # Shape 2: {"topics": [...]}
    topics = raw.get("topics") or []
    if isinstance(topics, list) and topics:
        result = []
        for t in topics:
            if isinstance(t, str):
                result.append({"chapter": "Document", "topic": t, "subtopics": []})
            elif isinstance(t, dict):
                t_title = t.get("title") or t.get("topic") or t.get("name") or "Topic"
                subs = t.get("subtopics") or []
                result.append({
                    "chapter": t.get("chapter", "Document"),
                    "topic": t_title,
                    "subtopics": [s if isinstance(s, str) else str(s) for s in subs],
                })
        if result:
            return result

    return []


def _outline_to_markdown_toc(outline: list[dict], filename: str) -> str:
    """Render the outline as a human-readable Markdown table of contents."""
    lines = [f"# Exam Notes — {filename}", "", "## Table of Contents", ""]
    last_chapter = None
    ch_num = 0
    t_num = 0
    for item in outline:
        ch = item.get("chapter", "")
        if ch != last_chapter:
            ch_num += 1
            t_num = 0
            lines.append(f"### Chapter {ch_num}: {ch}")
            last_chapter = ch
        t_num += 1
        lines.append(f"- {ch_num}.{t_num} {item['topic']}")
        for s_idx, sub in enumerate(item.get("subtopics", []), 1):
            lines.append(f"  - {ch_num}.{t_num}.{s_idx} {sub}")
    lines.append("")
    return "\n".join(lines)


def _build_topic_prompt(
    filename: str,
    chapter: str,
    topic: str,
    subtopics: list[str],
    context: str,
    topic_number: str,
) -> str:
    """Build the per-topic Granite prompt for Stage 2."""

    subtopic_block = ""
    if subtopics:
        numbered = "\n".join(f"  {topic_number}.{i+1} {s}" for i, s in enumerate(subtopics))
        subtopic_block = (
            f"\nSUBTOPICS TO COVER (each MUST have its own heading and explanation):\n"
            + numbered
            + "\n"
        )

    return (
        f"Document: {filename}\n"
        f"Chapter: {chapter}\n"
        f"Topic: {topic_number} {topic}\n"
        + subtopic_block
        + "\nTASK: Write detailed college exam notes for the topic above.\n\n"
        "Use this EXACT structure:\n\n"
        f"## {topic_number} {topic}\n\n"
        "**Introduction:**\n"
        "[2-3 sentences defining the topic and its importance in the subject area.]\n\n"
        + (
            "".join(
                f"### {topic_number}.{i+1} {sub}\n\n"
                "**Explanation:**\n"
                "[4-6 sentences: what it means, why it matters, how it works, "
                "key details from the source.]\n\n"
                "**Important Points:**\n"
                "- [Point 1 with brief explanation]\n"
                "- [Point 2 with brief explanation]\n"
                "- [Point 3 with brief explanation]\n\n"
                "**Example:**\n"
                "[One sentence example from the source, or mark '(General knowledge)'.]\n\n"
                for i, sub in enumerate(subtopics)
            )
            if subtopics else
            "**Explanation:**\n"
            "[4-6 sentences covering what it means, why it matters, how it works, "
            "and key details from the source.]\n\n"
            "**Important Points:**\n"
            "- [Point 1 with brief explanation]\n"
            "- [Point 2 with brief explanation]\n"
            "- [Point 3 with brief explanation]\n\n"
            "**Example:**\n"
            "[One sentence example from the source, or mark '(General knowledge)'.]\n\n"
        )
        + "---\n"
        "**Key Terms**\n"
        "- **[Term]:** [One-sentence definition.]\n\n"
        "**Exam Summary**\n"
        "1. [Key takeaway as a complete sentence.]\n"
        "2. [Key takeaway as a complete sentence.]\n"
        "3. [Key takeaway as a complete sentence.]\n\n"
        "RULES:\n"
        "- Replace every [...] placeholder with real content from the source.\n"
        "- Each subtopic heading MUST have its own Explanation, Important Points, "
        "and Example block.\n"
        "- Do NOT skip, merge, or abbreviate any subtopic.\n"
        "- Do NOT output bare keywords or one-liner bullets without explanation.\n"
        "- Use **bold** for technical terms on first use.\n\n"
        "SOURCE CONTENT:\n"
        + context
    )


class StudyMaterialAgent:
    def __init__(self, granite_service, vector_db_service):
        self.granite = granite_service
        self.vector_db = vector_db_service

    # ── Quick topic notes (unchanged) ─────────────────────────────────────────

    def run(self, query: str, analyzed_material: dict = None) -> dict:
        """Generate study material for *query* using ChromaDB context."""
        context_chunks = self.vector_db.search(query, n_results=5)

        context_parts = []
        for chunk in context_chunks:
            source = chunk.get("filename", "unknown source")
            text = chunk.get("text", "")
            context_parts.append(f"[Source: {source}]\n{text}")

        if context_parts:
            context_str = "\n\n".join(context_parts)
        else:
            context_str = "No uploaded documents found. Generate study material based on general knowledge."

        subject_hint = ""
        if analyzed_material and isinstance(analyzed_material, dict):
            subject = analyzed_material.get("subject", "")
            if subject and subject != "Unknown":
                subject_hint = f"Subject area: {subject}\n"

        context_str = context_str[:1500]

        prompt = (
            "Generate study material based on the content below.\n\n"
            + (f"Subject area: {subject_hint}\n" if subject_hint else "")
            + f"Topic: {query}\n\n"
            + "Study material from uploaded documents:\n"
            + context_str
            + "\n\n"
            "Output ONLY a JSON object with these exact keys (no other text):\n"
            '{\n'
            '  "notes": ["key point 1", "key point 2", "key point 3"],\n'
            '  "summary": "2-3 sentence summary of the topic",\n'
            '  "flashcards": [{"question": "Q?", "answer": "A."}],\n'
            '  "simplified_concepts": [{"concept": "name", "explanation": "simple explanation"}]\n'
            '}'
        )

        try:
            result = self.granite.generate_json(prompt, SYSTEM_PROMPT)
        except ValueError as exc:
            logger.warning("StudyMaterialAgent: JSON parse failed — %s", exc)
            return {
                **_KEY_DEFAULTS,
                "error": str(exc),
                "notes": [
                    f"Could not generate structured notes for '{query}'.",
                    "Please try a more specific query or re-upload the document.",
                ],
                "summary": f"Notes generation failed for query: {query}.",
            }

        for key, default in _KEY_DEFAULTS.items():
            if key not in result:
                result[key] = default

        return result

    # ── Detailed full-document exam notes — two-stage pipeline ────────────────

    def generate_detailed_notes(
        self,
        doc_id: str,
        filename: str,
        progress_callback=None,
    ) -> dict:
        """Generate comprehensive exam-oriented notes for the entire document.

        Stage 1 — Outline extraction:
            Sends the first portion of the document text to Granite and asks
            for a JSON outline: chapters > topics > subtopics.  The outline
            is treated as ground truth — every item in it will be covered.

        Stage 2 — Per-topic generation:
            For every topic in the outline, the relevant document chunks are
            retrieved from ChromaDB and a dedicated Granite call generates the
            CHAPTER / 1.1 / 1.1.1 structured notes for that topic only.

        Post-generation validation:
            Each outline item is checked for a matching generated section.
            Missing sections are flagged in coverage_stats.

        Parameters
        ----------
        doc_id:
            ChromaDB document ID (MD5 of filename).
        filename:
            Human-readable filename shown in the UI.
        progress_callback:
            Optional callable(current: int, total: int, hint: str).

        Returns
        -------
        dict with keys: sections, toc, full_markdown, total_batches,
                        filename, coverage_stats
        """
        # ── 1. Retrieve all ordered chunks ────────────────────────────────────
        all_chunks = self.vector_db.get_all_chunks_for_document(doc_id)

        if not all_chunks:
            return {
                "sections": [],
                "toc": [],
                "full_markdown": "",
                "total_batches": 0,
                "filename": filename,
                "coverage_stats": {},
                "error": (
                    f"No content found in the knowledge base for '{filename}'. "
                    "Please re-upload the document on the Upload page."
                ),
            }

        total_chunks = len(all_chunks)
        print(f"[StudyMaterialAgent] {total_chunks} chunks loaded for '{filename}'")

        # ── 2. Stage 1 — Extract outline ──────────────────────────────────────
        if progress_callback:
            try:
                progress_callback(0, 1, "Extracting document outline…")
            except Exception:
                pass

        outline = self._extract_outline(all_chunks, filename)

        # If outline extraction failed or returned nothing useful, fall back
        # to a flat single-topic outline covering the whole document.
        if not outline:
            logger.warning(
                "DetailedNotes: outline extraction returned nothing for '%s'. "
                "Falling back to flat batch processing.",
                filename,
            )
            outline = [{"chapter": filename, "topic": filename, "subtopics": []}]

        total_topics = len(outline)
        print(
            f"[StudyMaterialAgent] Outline: {total_topics} topics extracted for '{filename}'"
        )

        # ── 3. Stage 2 — Generate notes per topic ─────────────────────────────
        sections: list[dict] = []
        all_markdown_parts: list[str] = []

        # Assign chapter-relative numbers (ch_num.topic_num)
        last_chapter = None
        ch_num = 0
        t_num = 0

        for topic_idx, item in enumerate(outline):
            chapter = item.get("chapter", "")
            topic = item.get("topic", f"Topic {topic_idx + 1}")
            subtopics = item.get("subtopics", [])

            if chapter != last_chapter:
                ch_num += 1
                t_num = 0
                last_chapter = chapter
            t_num += 1
            topic_number = f"{ch_num}.{t_num}"

            hint = topic[:60]
            if progress_callback:
                try:
                    progress_callback(topic_idx + 1, total_topics, hint)
                except Exception:
                    pass

            # Retrieve relevant chunks for this topic via semantic search
            context = self._retrieve_context(topic, subtopics)

            # Build and run the generation prompt
            prompt = _build_topic_prompt(
                filename, chapter, topic, subtopics, context, topic_number
            )

            try:
                markdown_section = self.granite.generate(
                    prompt, _NOTES_SYSTEM_PROMPT, max_tokens=_TOPIC_MAX_TOKENS
                )
            except RuntimeError as exc:
                logger.warning(
                    "DetailedNotes topic '%s' failed: %s", topic, exc
                )
                markdown_section = (
                    f"## {topic_number} {topic}\n\n"
                    f"*Notes could not be generated for this topic: {exc}*"
                )

            # Extract the heading for the section tab (first ## line)
            heading = f"{topic_number} {topic}"
            for line in markdown_section.splitlines():
                stripped = line.strip()
                if stripped.startswith("## "):
                    heading = stripped[3:].strip()
                    break

            sections.append({
                "heading": heading,
                "content": markdown_section,
                "chapter": chapter,
                "topic": topic,
                "subtopics": subtopics,
            })
            all_markdown_parts.append(markdown_section)

        # ── 4. Post-generation validation ─────────────────────────────────────
        missing_sections: list[str] = []
        for item in outline:
            topic = item.get("topic", "")
            matched = any(
                topic.lower() in s.get("topic", "").lower()
                or topic.lower() in s.get("content", "").lower()[:200]
                for s in sections
            )
            if not matched:
                missing_sections.append(topic)

        if missing_sections:
            logger.warning(
                "DetailedNotes: %d outline topics have no matching section: %s",
                len(missing_sections), missing_sections
            )

        # Count ### subsections (excluding summary lines) across all output
        generated_subheadings = sum(
            1 for part in all_markdown_parts
            for line in part.splitlines()
            if line.strip().startswith("### ")
            and "summary" not in line.lower()
            and "key terms" not in line.lower()
        )

        coverage_stats = {
            "total_chunks": total_chunks,
            "outline_topics": total_topics,
            "generated_sections": len(sections),
            "generated_subheadings": generated_subheadings,
            "missing_sections": missing_sections,
            "coverage_pct": round(
                100 * (total_topics - len(missing_sections)) / max(total_topics, 1)
            ),
        }

        # ── 5. Assemble final result ───────────────────────────────────────────
        toc_md = _outline_to_markdown_toc(outline, filename)
        full_markdown = (
            toc_md
            + "\n\n---\n\n"
            + "\n\n---\n\n".join(all_markdown_parts)
        )

        return {
            "sections": sections,
            "toc": [s["heading"] for s in sections],
            "full_markdown": full_markdown,
            "total_batches": total_topics,
            "filename": filename,
            "coverage_stats": coverage_stats,
        }

    # ── Private helpers ────────────────────────────────────────────────────────

    def _extract_outline(self, all_chunks: list[str], filename: str) -> list[dict]:
        """Stage 1: ask Granite to return a structured JSON outline of the document.

        Sends the first _OUTLINE_CHARS characters of the joined document text.
        Returns a normalised list of outline items (see _clean_outline).
        """
        # Combine the first several chunks to get a representative overview
        preview_text = "\n\n".join(all_chunks)[:_OUTLINE_CHARS]

        prompt = (
            f"Document filename: {filename}\n\n"
            "Analyze the table of contents, headings, and structure of the document "
            "excerpt below. Extract a complete hierarchical outline.\n\n"
            "Output ONLY a JSON object in this exact format:\n"
            "{\n"
            '  "chapters": [\n'
            "    {\n"
            '      "title": "Chapter 1: Introduction",\n'
            '      "topics": [\n'
            "        {\n"
            '          "title": "1.1 Background",\n'
            '          "subtopics": ["1.1.1 History", "1.1.2 Motivation"]\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Include EVERY chapter, section, and subsection you can identify.\n"
            "- Use the actual heading text from the document, not generic placeholders.\n"
            "- If there are no explicit chapters, group topics logically.\n"
            "- Do NOT include page numbers, figures, or references sections.\n\n"
            "DOCUMENT EXCERPT:\n"
            + preview_text
        )

        try:
            raw = self.granite.generate_json(prompt, _OUTLINE_SYSTEM_PROMPT, max_tokens=1500)
        except (ValueError, RuntimeError) as exc:
            logger.warning("DetailedNotes: Stage 1 outline extraction failed: %s", exc)
            return []

        outline = _clean_outline(raw)
        print(
            f"[StudyMaterialAgent] Stage 1 outline: {len(outline)} items "
            f"(raw keys: {list(raw.keys())})"
        )
        return outline

    def _retrieve_context(self, topic: str, subtopics: list[str]) -> str:
        """Retrieve relevant document chunks for *topic* + *subtopics*.

        Performs a semantic search for the topic and, if subtopics exist,
        for each subtopic individually, then deduplicates and concatenates
        the results up to _MAX_CONTEXT_CHARS characters.
        """
        seen_texts: set[str] = set()
        context_parts: list[str] = []

        # Search queries: the topic itself, then each subtopic
        queries = [topic] + subtopics[:3]

        for query in queries:
            results = self.vector_db.search(query, n_results=_CHUNKS_PER_TOPIC)
            for chunk in results:
                text = chunk.get("text", "")
                # Deduplicate by first 100 chars
                key = text[:100]
                if key and key not in seen_texts:
                    seen_texts.add(key)
                    context_parts.append(text)

        combined = "\n\n".join(context_parts)
        return combined[:_MAX_CONTEXT_CHARS]
