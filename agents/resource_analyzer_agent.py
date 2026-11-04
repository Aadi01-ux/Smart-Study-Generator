"""Agent 1 — Resource Analyzer Agent.

Extracts text from an uploaded document, embeds it in ChromaDB, and
calls IBM Granite to produce a structured analysis (subject, topics,
subtopics, definitions, key_concepts).
"""

import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert academic resource analyzer. Your only output is a single "
    "valid JSON object — no prose, no markdown, no code fences. "
    "Analyze the provided study material and extract structured information."
)

REQUIRED_KEYS = {"subject", "topics", "subtopics", "definitions", "key_concepts"}


class ResourceAnalyzerAgent:
    def __init__(self, granite_service, vector_db_service, document_service):
        self.granite = granite_service
        self.vector_db = vector_db_service
        self.document = document_service

    def run(self, file_bytes: bytes, filename: str) -> dict:
        """Extract, embed, and analyze a study document.

        Returns a dict with keys:
            subject, topics, subtopics, definitions, key_concepts,
            doc_id, filename, skipped
        """
        # Step 1 & 2 — extract text and derive a stable doc_id
        try:
            text = self.document.extract_text(file_bytes, filename)
        except ValueError as exc:
            raise ValueError(
                f"ResourceAnalyzerAgent: could not extract text from '{filename}': {exc}"
            ) from exc

        doc_id = self.document.generate_doc_id(filename)

        # Step 3 — chunk the text
        chunks = self.document.chunk_text(text)

        # Step 4 — embed chunks in ChromaDB (skip if duplicate)
        was_added = self.vector_db.add_document(doc_id, chunks, filename)
        skipped = not was_added

        # Step 5 — build the analysis prompt.
        # Truncate text to ~3000 chars; leave headroom for the JSON output tokens.
        truncated = text[:3000] if len(text) > 3000 else text
        prompt = (
            "Analyze the study material below and extract structured information.\n\n"
            f"Document filename: {filename}\n\n"
            f"Content:\n{truncated}\n\n"
            "Output ONLY a JSON object with these exact keys (no other text):\n"
            '{\n'
            '  "subject": "the main academic subject or course name",\n'
            '  "topics": ["main topic 1", "main topic 2"],\n'
            '  "subtopics": {"topic1": ["subtopic1", "subtopic2"]},\n'
            '  "definitions": [{"term": "term name", "definition": "definition text"}],\n'
            '  "key_concepts": ["important concept 1", "important concept 2"]\n'
            '}'
        )

        # Step 6 — call Granite
        try:
            result = self.granite.generate_json(prompt, SYSTEM_PROMPT)
        except RuntimeError as exc:
            raise RuntimeError(
                f"ResourceAnalyzerAgent: Granite generation failed for '{filename}': {exc}"
            ) from exc
        except ValueError:
            # Invalid JSON returned — return a graceful error dict
            return {
                "error": "Granite returned invalid JSON during resource analysis.",
                "subject": "Unknown",
                "topics": [],
                "subtopics": {},
                "definitions": [],
                "key_concepts": [],
                "doc_id": doc_id,
                "filename": filename,
                "skipped": skipped,
            }

        # Step 7 — validate required keys
        missing = REQUIRED_KEYS - result.keys()
        if missing:
            for key in missing:
                result.setdefault(key, [] if key != "subject" else "Unknown")
                if key == "subtopics":
                    result[key] = {}

        # Step 8 — attach metadata
        result["doc_id"] = doc_id
        result["filename"] = filename
        result["skipped"] = skipped

        return result
