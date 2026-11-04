"""
services/storage_service.py — persistent JSON storage for quiz results, study plans,
progress records, and flashcard results.
"""

import json
import os
from datetime import datetime

import config

# File names within JSON_DATA_PATH
_QUIZ_RESULTS_FILE = "quiz_results.json"
_STUDY_PLAN_FILE = "study_plan.json"
_PROGRESS_FILE = "progress.json"
_FLASHCARD_RESULTS_FILE = "flashcard_results.json"


class StorageService:
    """Read/write helper for all persistent structured data."""

    def __init__(self) -> None:
        os.makedirs(config.JSON_DATA_PATH, exist_ok=True)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load(self, filename: str):
        """Load JSON from *filename* inside JSON_DATA_PATH.

        Returns [] for list-type files and {} for dict-type files when the
        file does not exist.  The default is determined by the file extension
        convention: any file whose base name contains 'results' is a list,
        everything else is a dict.
        """
        path = os.path.join(config.JSON_DATA_PATH, filename)
        if not os.path.exists(path):
            # Infer default type from filename
            if "results" in filename:
                return []
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, filename: str, data) -> None:
        """Serialise *data* as JSON and write to *filename*."""
        os.makedirs(config.JSON_DATA_PATH, exist_ok=True)
        path = os.path.join(config.JSON_DATA_PATH, filename)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    # ── Quiz results (list) ───────────────────────────────────────────────────

    def save_quiz_result(self, result: dict) -> None:
        """Append *result* (with a timestamp) to quiz_results.json."""
        results = self._load(_QUIZ_RESULTS_FILE)
        results.append({**result, "timestamp": datetime.now().isoformat()})
        self._save(_QUIZ_RESULTS_FILE, results)

    def load_quiz_results(self) -> list[dict]:
        """Return all stored quiz results."""
        return self._load(_QUIZ_RESULTS_FILE)

    # ── Study plan (dict) ─────────────────────────────────────────────────────

    def save_study_plan(self, plan: dict) -> None:
        """Overwrite study_plan.json with *plan*."""
        self._save(_STUDY_PLAN_FILE, plan)

    def load_study_plan(self) -> dict:
        """Return the stored study plan, or {} if none exists."""
        return self._load(_STUDY_PLAN_FILE)

    # ── Progress (dict) ───────────────────────────────────────────────────────

    def save_progress(self, progress: dict) -> None:
        """Overwrite progress.json with *progress*."""
        self._save(_PROGRESS_FILE, progress)

    def load_progress(self) -> dict:
        """Return the stored progress record, or {} if none exists."""
        return self._load(_PROGRESS_FILE)

    # ── Flashcard results (list) ──────────────────────────────────────────────

    def save_flashcard_result(self, result: dict) -> None:
        """Append *result* (with a timestamp) to flashcard_results.json."""
        results = self._load(_FLASHCARD_RESULTS_FILE)
        results.append({**result, "timestamp": datetime.now().isoformat()})
        self._save(_FLASHCARD_RESULTS_FILE, results)

    def load_flashcard_results(self) -> list[dict]:
        """Return all stored flashcard results."""
        return self._load(_FLASHCARD_RESULTS_FILE)


# ── Module-level singleton ────────────────────────────────────────────────────

_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    """Return the shared StorageService instance (created on first call)."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
