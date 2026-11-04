"""Agent 3 — Assessment Agent.

Generates multiple-choice quiz questions from ChromaDB context and
evaluates student answers to identify weak topics.
"""

import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert assessment creator. Your only output is a single "
    "valid JSON object — no prose, no markdown, no code fences. "
    "Generate clear, educational multiple-choice questions with accurate answers."
)


class AssessmentAgent:
    def __init__(self, granite_service, vector_db_service):
        self.granite = granite_service
        self.vector_db = vector_db_service

    # ------------------------------------------------------------------
    # Quiz generation
    # ------------------------------------------------------------------

    def run(self, topic: str) -> dict:
        """Generate 5 MCQ questions for *topic* using ChromaDB context.

        Returns a dict with keys: topic, questions.
        Each question has: id, question, options (A/B/C/D), correct_answer,
        explanation.
        """
        # Step 1 — retrieve relevant context
        context_chunks = self.vector_db.search(topic, n_results=5)

        context_parts = []
        for chunk in context_chunks:
            source = chunk.get("filename", "unknown source")
            text = chunk.get("text", "")
            context_parts.append(f"[Source: {source}]\n{text}")
        context_str = (
            "\n\n".join(context_parts) if context_parts else "No additional context available."
        )

        # Step 2 — build prompt. Cap context to avoid prompt overflow.
        context_str = context_str[:1500]
        prompt = (
            f"Generate exactly 5 multiple-choice questions about: {topic}\n\n"
            "Study material context:\n"
            + context_str
            + "\n\n"
            "Output ONLY a JSON object with these exact keys (no other text):\n"
            '{\n'
            f'  "topic": "{topic}",\n'
            '  "questions": [\n'
            '    {\n'
            '      "id": 1,\n'
            '      "question": "question text here",\n'
            '      "options": {"A": "first option", "B": "second option", "C": "third option", "D": "fourth option"},\n'
            '      "correct_answer": "A",\n'
            '      "explanation": "explanation of why A is correct"\n'
            '    }\n'
            "  ]\n"
            "}"
        )

        # Step 3 — call Granite
        try:
            result = self.granite.generate_json(prompt, SYSTEM_PROMPT)
        except ValueError as exc:
            logger.warning("AssessmentAgent: JSON parse failed — %s", exc)
            raise ValueError(
                f"AssessmentAgent: could not generate quiz for topic '{topic}'. "
                "Try a more specific topic or ensure documents are uploaded."
            ) from exc

        # Step 4 — validate; fill missing keys with safe defaults
        if "questions" not in result:
            result["questions"] = []
        if not isinstance(result["questions"], list) or len(result["questions"]) == 0:
            raise ValueError(
                f"AssessmentAgent: Granite returned no questions for topic '{topic}'. "
                "Ensure relevant documents are uploaded before generating a quiz."
            )
        if "topic" not in result:
            result["topic"] = topic

        return result

    # ------------------------------------------------------------------
    # Quiz evaluation
    # ------------------------------------------------------------------

    def evaluate(self, questions: list, student_answers: list) -> dict:
        """Score a completed quiz and identify weak topics.

        Parameters
        ----------
        questions:
            List of question dicts as returned by run() (each has id,
            question, options, correct_answer, explanation).
        student_answers:
            List of answer strings (e.g. ["A", "C", "B", "D", "A"])
            in the same order as *questions*.

        Returns a dict with keys: score, correct, total, weak_topics,
        per_question.
        """
        total = len(questions)
        correct_count = 0
        weak_topics = []
        per_question = []

        for i, question in enumerate(questions):
            student_ans = student_answers[i] if i < len(student_answers) else None
            correct_ans = question.get("correct_answer", "")
            is_correct = student_ans == correct_ans

            if is_correct:
                correct_count += 1
            else:
                # Use the question text as a proxy for the weak topic
                weak_topics.append(question.get("question", f"Question {i + 1}"))

            per_question.append(
                {
                    "question_id": question.get("id", i + 1),
                    "correct": is_correct,
                    "student_answer": student_ans,
                    "correct_answer": correct_ans,
                    "explanation": question.get("explanation", ""),
                }
            )

        score_percent = round((correct_count / total) * 100, 1) if total > 0 else 0.0

        return {
            "score": score_percent,
            "correct": correct_count,
            "total": total,
            "weak_topics": weak_topics,
            "per_question": per_question,
        }
