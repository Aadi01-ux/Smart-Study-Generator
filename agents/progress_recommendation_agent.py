"""Agent 5 — Progress & Recommendation Agent.

Analyses quiz history and completed topics to produce a personalised
learning report with strong/weak topics, performance trend, milestones,
and actionable next-step recommendations.
"""

import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert learning coach and progress analyzer. Your only output "
    "is a single valid JSON object — no prose, no markdown, no code fences. "
    "Analyze student performance data and provide personalized recommendations."
)

REQUIRED_KEYS = {
    "strong_topics",
    "weak_topics",
    "average_score",
    "performance_trend",
    "milestones",
    "recommendations",
    "next_topic",
}

# Safe defaults for each required key
_KEY_DEFAULTS: dict = {
    "strong_topics": [],
    "weak_topics": [],
    "average_score": 0.0,
    "performance_trend": "stable",
    "milestones": [],
    "recommendations": ["Keep practicing and reviewing your study material."],
    "next_topic": "Review previous quiz topics",
}


class ProgressRecommendationAgent:
    def __init__(self, granite_service, vector_db_service):
        self.granite = granite_service
        self.vector_db = vector_db_service

    def run(
        self,
        quiz_results: list,
        completed_topics: list,
        all_topics: list,
        context_query: str = None,
    ) -> dict:
        """Analyse learning progress and return personalised recommendations.

        Parameters
        ----------
        quiz_results:
            List of quiz result dicts, each expected to contain at least
            ``score`` (numeric 0-100) and optionally ``weak_topics``
            (list of question texts where the student failed).
        completed_topics:
            Topics the student has already studied.
        all_topics:
            The full list of topics for the subject.
        context_query:
            If provided, ChromaDB is searched with this query to enrich the
            recommendation with relevant study content.

        Returns a dict with keys: strong_topics, weak_topics, average_score,
        performance_trend, milestones, recommendations, next_topic.
        """
        # ----------------------------------------------------------------
        # Step 1 — optional ChromaDB search for enriched context
        # ----------------------------------------------------------------
        context_str = ""
        if context_query:
            try:
                context_chunks = self.vector_db.search(context_query, n_results=3)
                if context_chunks:
                    parts = [
                        f"[Source: {c.get('filename', 'unknown')}]\n{c.get('text', '')}"
                        for c in context_chunks
                    ]
                    context_str = "\n\n".join(parts)
            except Exception:
                # ChromaDB search is optional — never fail hard here
                context_str = ""

        # ----------------------------------------------------------------
        # Step 2 — compute basic statistics from quiz_results
        # ----------------------------------------------------------------
        scores = [r.get("score", 0) for r in quiz_results if isinstance(r, dict)]
        average_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        # Score trend: compare first half vs second half
        trend = "stable"
        if len(scores) >= 2:
            mid = len(scores) // 2
            first_half_avg = sum(scores[:mid]) / mid
            second_half_avg = sum(scores[mid:]) / (len(scores) - mid)
            if second_half_avg > first_half_avg + 5:
                trend = "improving"
            elif second_half_avg < first_half_avg - 5:
                trend = "declining"

        # Aggregate weak topics across all quizzes
        all_weak: dict[str, int] = {}
        for r in quiz_results:
            for wt in r.get("weak_topics", []):
                all_weak[wt] = all_weak.get(wt, 0) + 1
        # Sort by frequency descending
        sorted_weak = sorted(all_weak, key=lambda k: all_weak[k], reverse=True)

        # ----------------------------------------------------------------
        # Step 3 — build prompt
        # ----------------------------------------------------------------
        remaining_topics = [t for t in all_topics if t not in completed_topics]
        completed_str = ", ".join(completed_topics) if completed_topics else "none yet"
        remaining_str = ", ".join(remaining_topics) if remaining_topics else "all topics covered"
        weak_str = ", ".join(sorted_weak[:5]) if sorted_weak else "none identified"

        context_section = (
            f"\nRelevant study material context:\n{context_str}\n"
            if context_str
            else ""
        )

        prompt = (
            "Analyze the student performance data below and give recommendations.\n\n"
            f"Total quizzes taken: {len(quiz_results)}\n"
            f"Average score: {average_score}%\n"
            f"Score trend: {trend}\n"
            f"Completed topics: {completed_str}\n"
            f"Remaining topics: {remaining_str}\n"
            f"Recurring weak topics: {weak_str}\n"
            f"Score history: {scores}\n"
            f"{context_section}\n"
            "Output ONLY a JSON object with these exact keys (no other text):\n"
            '{\n'
            '  "strong_topics": ["topic the student knows well"],\n'
            '  "weak_topics": ["topic needing improvement"],\n'
            f'  "average_score": {average_score},\n'
            f'  "performance_trend": "{trend}",\n'
            '  "milestones": ["Completed first quiz", "Scored above 70%"],\n'
            '  "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"],\n'
            '  "next_topic": "the single most important topic to study next"\n'
            "}"
        )

        # ----------------------------------------------------------------
        # Step 4 — call Granite
        # ----------------------------------------------------------------
        try:
            result = self.granite.generate_json(prompt, SYSTEM_PROMPT)
        except ValueError as exc:
            logger.warning("ProgressRecommendationAgent: JSON parse failed — %s", exc)
            # Return a graceful fallback with computed stats intact
            return {
                **_KEY_DEFAULTS,
                "average_score": average_score,
                "performance_trend": trend,
                "weak_topics": sorted_weak[:5],
                "error": str(exc),
            }

        # ----------------------------------------------------------------
        # Step 5 — fill missing keys with safe defaults instead of raising
        # ----------------------------------------------------------------
        for key, default in _KEY_DEFAULTS.items():
            if key not in result:
                logger.warning(
                    "ProgressRecommendationAgent: key '%s' missing, using default.", key
                )
                result[key] = default

        return result
