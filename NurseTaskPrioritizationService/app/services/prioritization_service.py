"""Service layer for nursing task prioritization."""
import logging
from datetime import datetime

from app.models.schemas import (
    TaskPrioritizationRequest,
    TaskPrioritizationResponse,
    PrioritizedTask,
)
from app.ai.client import AIClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class PrioritizationService:
    """Service for handling nursing task prioritization requests."""

    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()

    def process_request(self, request: TaskPrioritizationRequest) -> TaskPrioritizationResponse:
        """
        Process a task prioritization request.

        Args:
            request: Task prioritization request with patients and context

        Returns:
            Task prioritization response with prioritized tasks
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing prioritization request {request_id}")

            request_data = request.model_dump()

            logger.info(f"Request data: {len(request.patients)} patients")

            tasks_raw = self.ai_client.prioritize_tasks(request_data)

            prioritized_tasks = [
                PrioritizedTask(
                    rank=t.get("rank", i + 1),
                    patient_id=t.get("patient_id", ""),
                    room=t.get("room", ""),
                    task_id=t.get("task_id", ""),
                    task_type=t.get("task_type", "nursing_task"),
                    title=t.get("title", ""),
                    reason=t.get("reason", ""),
                    urgency=t.get("urgency", "medium"),
                    recommended_timeframe=t.get("recommended_timeframe", "as_able"),
                    source_signals=t.get("source_signals", []),
                )
                for i, t in enumerate(tasks_raw)
            ]

            patient_count = len(request.patients)
            task_count = len(prioritized_tasks)

            response = TaskPrioritizationResponse(
                request_id=request_id,
                prioritized_tasks=prioritized_tasks,
                summary="Task prioritization generated successfully.",
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "patient_count": patient_count,
                    "task_count": task_count,
                    "provider": "openai",
                    "api_version": "v1",
                },
            )

            logger.info(f"Prioritization completed for request {request_id}: {task_count} tasks")
            return response

        except ValueError as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing request {request.request_id}: {e}")
            raise ValueError(f"Task prioritization failed: {str(e)}")
