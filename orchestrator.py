from granite_service import get_granite_service, RateLimitError
from services.document_service import DocumentService
from services.storage_service import get_storage_service
from services.vector_database_service import get_vector_db_service
from agents.resource_analyzer_agent import ResourceAnalyzerAgent
from agents.study_material_agent import StudyMaterialAgent
from agents.assessment_agent import AssessmentAgent
from agents.study_planner_agent import StudyPlannerAgent
from agents.progress_recommendation_agent import ProgressRecommendationAgent

# Human-readable message shown in the UI when the free quota is exhausted.
_RATE_LIMIT_MSG = (
    "IBM watsonx.ai free usage limit reached. "
    "Please wait a few minutes and try again later."
)


def _rate_limit_result(agent_name: str) -> dict:
    """Return a structured error dict for 429 / consumption_limit_reached."""
    return {
        "agent_name": agent_name,
        "agent_status": "rate_limit",
        "error": _RATE_LIMIT_MSG,
    }


class Orchestrator:
    def __init__(self):
        self.granite = get_granite_service()
        self.document_service = DocumentService()
        self.storage = get_storage_service()
        self.vector_db = get_vector_db_service()
        self.agent1 = ResourceAnalyzerAgent(self.granite, self.vector_db, self.document_service)
        self.agent2 = StudyMaterialAgent(self.granite, self.vector_db)
        self.agent3 = AssessmentAgent(self.granite, self.vector_db)
        self.agent4 = StudyPlannerAgent(self.granite)
        self.agent5 = ProgressRecommendationAgent(self.granite, self.vector_db)

    def process_document(self, file_bytes: bytes, filename: str) -> dict:
        agent_name = "Resource Analyzer Agent"
        try:
            result = self.agent1.run(file_bytes, filename)
            return {"agent_name": agent_name, "agent_status": "success", **result}
        except RateLimitError as e:
            print(f"[{agent_name}] RateLimitError: {e}")
            return _rate_limit_result(agent_name)
        except ValueError as e:
            print(f"[{agent_name}] ValueError: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}
        except RuntimeError as e:
            print(f"[{agent_name}] RuntimeError: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}

    def generate_study_material(self, query: str, analyzed_material: dict = None) -> dict:
        agent_name = "Study Material Generator"
        try:
            result = self.agent2.run(query, analyzed_material)
            return {"agent_name": agent_name, "agent_status": "success", **result}
        except RateLimitError as e:
            print(f"[{agent_name}] RateLimitError: {e}")
            return _rate_limit_result(agent_name)
        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}

    def generate_quiz(self, topic: str) -> dict:
        agent_name = "Assessment Agent"
        try:
            result = self.agent3.run(topic)
            return {"agent_name": agent_name, "agent_status": "success", **result}
        except RateLimitError as e:
            print(f"[{agent_name}] RateLimitError: {e}")
            return _rate_limit_result(agent_name)
        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}

    def evaluate_quiz(self, questions: list, student_answers: list) -> dict:
        agent_name = "Assessment Agent"
        try:
            result = self.agent3.evaluate(questions, student_answers)
            self.storage.save_quiz_result(result)
            return {"agent_name": agent_name, "agent_status": "success", **result}
        except RateLimitError as e:
            print(f"[{agent_name}] RateLimitError: {e}")
            return _rate_limit_result(agent_name)
        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}

    def generate_study_plan(
        self,
        subject: str,
        exam_date: str,
        hours_per_day: float,
        topics: list,
    ) -> dict:
        agent_name = "Study Planner Agent"
        try:
            progress = self.storage.load_progress()
            weak_topics = progress.get("weak_topics", [])
            result = self.agent4.run(subject, exam_date, hours_per_day, topics, weak_topics)
            self.storage.save_study_plan(result)
            return {"agent_name": agent_name, "agent_status": "success", **result}
        except RateLimitError as e:
            print(f"[{agent_name}] RateLimitError: {e}")
            return _rate_limit_result(agent_name)
        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}

    def get_progress_report(self) -> dict:
        agent_name = "Progress & Recommendation Agent"
        try:
            quiz_results = self.storage.load_quiz_results()
            progress = self.storage.load_progress()
            completed_topics = progress.get("completed_topics", [])
            all_topics = progress.get("all_topics", [])
            weak_topics = progress.get("weak_topics", [])
            context_query = (
                "weak topics: " + ", ".join(weak_topics) if weak_topics else None
            )
            result = self.agent5.run(quiz_results, completed_topics, all_topics, context_query)
            self.storage.save_progress(result)
            return {"agent_name": agent_name, "agent_status": "success", **result}
        except RateLimitError as e:
            print(f"[{agent_name}] RateLimitError: {e}")
            return _rate_limit_result(agent_name)
        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}

    def generate_detailed_notes(self, doc_id: str, filename: str, progress_callback=None) -> dict:
        """Generate comprehensive full-document exam notes via Agent 2's pipeline."""
        agent_name = "Study Material Generator"
        try:
            result = self.agent2.generate_detailed_notes(
                doc_id, filename, progress_callback=progress_callback
            )
            return {"agent_name": agent_name, "agent_status": "success", **result}
        except RateLimitError as e:
            print(f"[{agent_name}] RateLimitError: {e}")
            return _rate_limit_result(agent_name)
        except Exception as e:
            print(f"[{agent_name}] generate_detailed_notes error: {e}")
            return {"agent_name": agent_name, "agent_status": "error", "error": str(e)}

    def list_uploaded_documents(self) -> list:
        return self.vector_db.list_documents()

    def delete_document(self, doc_id: str) -> dict:
        """Remove all chunks for *doc_id* from the vector database."""
        try:
            self.vector_db.delete_document(doc_id)
            return {"status": "deleted", "doc_id": doc_id}
        except Exception as e:
            return {"status": "error", "doc_id": doc_id, "error": str(e)}


_orchestrator_instance = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = Orchestrator()
    return _orchestrator_instance
