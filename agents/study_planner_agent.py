"""Agent 4 — Study Planner Agent.

Takes the student's subject, exam date, daily study hours, topic list,
and (optionally) weak topics, then calls IBM Granite to produce a
personalized daily study schedule.

Note: This agent does NOT access ChromaDB directly — it receives all
inputs from the orchestrator.
"""

import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert academic study planner. Your only output is a single "
    "valid JSON object — no prose, no markdown, no code fences. "
    "Create personalized, realistic study schedules that prioritize weak topics."
)


class StudyPlannerAgent:
    def __init__(self, granite_service):
        self.granite = granite_service

    def run(
        self,
        subject: str,
        exam_date: str,
        hours_per_day: float,
        topics: list,
        weak_topics: list = None,
    ) -> dict:
        """Generate a personalized daily study plan.

        Parameters
        ----------
        subject:
            The academic subject (e.g. "Data Structures").
        exam_date:
            Target exam date in any human-readable format (e.g. "2024-12-15").
        hours_per_day:
            Number of study hours available each day.
        topics:
            Full list of topics to cover before the exam.
        weak_topics:
            Topics where the student scored poorly in previous quizzes.
            These should be prioritized in the schedule.

        Returns a dict with keys: subject, exam_date, total_days,
        daily_plan, study_tips.
        """
        weak_topics = weak_topics or []

        topics_str = "\n".join(f"  - {t}" for t in topics) if topics else "  - (no topics provided)"
        weak_str = (
            "\n".join(f"  - {t}" for t in weak_topics)
            if weak_topics
            else "  - none identified yet"
        )

        # Step 1 — build the planning prompt.
        prompt = (
            "Create a daily study plan for the following student.\n\n"
            f"Subject: {subject}\n"
            f"Exam Date: {exam_date}\n"
            f"Study hours per day: {hours_per_day}\n\n"
            f"Topics to cover:\n{topics_str}\n\n"
            f"Weak topics needing extra time:\n{weak_str}\n\n"
            "Rules:\n"
            "- Spread topics across the days before the exam.\n"
            "- Give weak topics more days or hours.\n"
            "- Add a revision day before the exam.\n\n"
            "Output ONLY a JSON object with these exact keys (no other text):\n"
            '{\n'
            f'  "subject": "{subject}",\n'
            f'  "exam_date": "{exam_date}",\n'
            '  "total_days": 7,\n'
            '  "daily_plan": [\n'
            '    {\n'
            '      "day": 1,\n'
            '      "date": "YYYY-MM-DD",\n'
            '      "topics": ["topic name"],\n'
            f'      "hours": {hours_per_day},\n'
            '      "activities": ["Read and take notes", "Practice problems", "Review flashcards"],\n'
            '      "priority": "high"\n'
            '    }\n'
            "  ],\n"
            '  "study_tips": ["Study tip 1", "Study tip 2"]\n'
            "}"
        )

        # Step 2 — call Granite
        try:
            result = self.granite.generate_json(prompt, SYSTEM_PROMPT)
        except ValueError as exc:
            logger.warning("StudyPlannerAgent: JSON parse failed — %s", exc)
            raise ValueError(
                f"StudyPlannerAgent: could not generate study plan. "
                "Please try again with fewer topics."
            ) from exc

        # Step 3 — validate and fill missing keys
        if "daily_plan" not in result or not isinstance(result["daily_plan"], list):
            logger.warning("StudyPlannerAgent: 'daily_plan' missing or not a list — using empty fallback.")
            result["daily_plan"] = []
        if "study_tips" not in result:
            result["study_tips"] = []
        result.setdefault("subject", subject)
        result.setdefault("exam_date", exam_date)
        result.setdefault("total_days", len(result["daily_plan"]))

        return result
