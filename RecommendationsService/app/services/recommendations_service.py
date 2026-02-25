"""Service layer for clinical recommendations generation."""
import logging
from typing import Dict, Any, List
from datetime import datetime

from app.models.schemas import (
    RecommendationRequest,
    RecommendationsResponse,
    ClinicalRecommendation,
    RecommendationPriority,
    SpecialtyConsultationRequest,
    SpecialtyConsultationResponse,
    ConsultationAction,
    UserRoleRecommendationRequest,
)
from app.ai.client import AIClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class RecommendationsService:
    """Service for handling clinical recommendations generation requests."""
    
    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()
    
    def process_request(self, request: RecommendationRequest) -> RecommendationsResponse:
        """
        Process a recommendations generation request.
        
        Args:
            request: Recommendations request with patient context
            
        Returns:
            Recommendations response with generated clinical recommendations
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing recommendations request {request_id}")
            
            # Convert patient context to dict
            patient_context_dict = request.patient_context.dict()
            
            # Convert recommendation types to strings
            rec_types = [rt.value if hasattr(rt, 'value') else str(rt) for rt in request.recommendation_types]
            
            # Log input data (for debugging)
            logger.info(f"Patient context: {patient_context_dict}")
            logger.info(f"Requested recommendation types: {rec_types}")
            
            # Step 1: Generate recommendations using AI client
            logger.info("Generating clinical recommendations with OpenAI...")
            ai_response = self.ai_client.generate_recommendations(
                patient_context=patient_context_dict,
                recommendation_types=rec_types,
                focus_areas=request.focus_areas
            )
            
            # Step 2: Parse recommendations into structured objects
            recommendations = self.ai_client.parse_recommendations(ai_response)
            
            logger.info(f"Generated {len(recommendations)} recommendations for request {request_id}")
            
            # Step 3: Calculate priority breakdown
            priority_breakdown = self._calculate_priority_breakdown(recommendations)
            
            # Step 4: Get summary from AI response or generate one
            summary = ai_response.get("summary", self._generate_summary(recommendations))
            
            # Step 5: Build response
            response = RecommendationsResponse(
                request_id=request_id,
                recommendations=recommendations,
                summary=summary,
                total_recommendations=len(recommendations),
                priority_breakdown=priority_breakdown,
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "recommendation_types_requested": rec_types,
                    "provider": "openai",
                    "api_version": "v1"
                }
            )
            
            return response
            
        except ValueError as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing request {request.request_id}: {e}")
            raise ValueError(f"Recommendations generation failed: {str(e)}")
    
    def _calculate_priority_breakdown(self, recommendations: List[ClinicalRecommendation]) -> Dict[str, int]:
        """Calculate count of recommendations by priority level."""
        breakdown = {
            "critical": 0,
            "high": 0,
            "moderate": 0,
            "low": 0,
            "routine": 0
        }
        
        for rec in recommendations:
            priority = rec.priority.value
            breakdown[priority] = breakdown.get(priority, 0) + 1
        
        return breakdown
    
    def _generate_summary(self, recommendations: List[ClinicalRecommendation]) -> str:
        """Generate a summary if AI didn't provide one."""
        if not recommendations:
            return "No recommendations generated."
        
        total = len(recommendations)
        critical = sum(1 for r in recommendations if r.priority == RecommendationPriority.CRITICAL)
        high = sum(1 for r in recommendations if r.priority == RecommendationPriority.HIGH)
        
        summary = f"Generated {total} clinical recommendation(s). "
        
        if critical > 0:
            summary += f"{critical} critical, "
        if high > 0:
            summary += f"{high} high priority. "
        
        summary += "Please review all recommendations below."
        
        return summary

    def process_specialty_consultation(
        self, request: SpecialtyConsultationRequest
    ) -> SpecialtyConsultationResponse:
        """Generate specialty consultation as a set of actions considering full patient context."""
        request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if request.patient_context:
            patient_context = getattr(request.patient_context, "model_dump", request.patient_context.dict)()
        else:
            patient_context = {}
        ai_response = self.ai_client.generate_specialty_recommendations(
            specialty=request.specialty,
            patient_context=patient_context,
            complaint=request.complaint,
        )
        summary = ai_response.get("summary", ai_response.get("content", str(ai_response)))
        if isinstance(summary, dict):
            summary = summary.get("summary", str(summary))
        actions_raw = ai_response.get("actions", [])
        actions: List[ConsultationAction] = []
        if isinstance(actions_raw, list):
            for idx, a in enumerate(actions_raw):
                try:
                    if isinstance(a, dict):
                        actions.append(ConsultationAction(
                            title=a.get("title", f"Action {idx + 1}"),
                            description=a.get("description"),
                            category=a.get("category"),
                            priority=a.get("priority"),
                        ))
                    else:
                        actions.append(ConsultationAction(title=str(a), description=None, category=None, priority=None))
                except Exception as e:
                    logger.warning(f"Skip invalid consultation action at {idx}: {e}")
        return SpecialtyConsultationResponse(request_id=request_id, summary=summary, actions=actions)

    def process_user_role_recommendations(
        self, request: UserRoleRecommendationRequest
    ) -> RecommendationsResponse:
        """Generate recommendations from user's specialty/role perspective."""
        request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        patient_context_dict = request.patient_context.dict()
        rec_types = [
            rt.value if hasattr(rt, "value") else str(rt)
            for rt in request.recommendation_types
        ]
        ai_response = self.ai_client.generate_role_based_recommendations(
            user_role=request.user_role,
            patient_context=patient_context_dict,
            recommendation_types=rec_types,
            focus_areas=request.focus_areas,
        )
        recommendations = self.ai_client.parse_recommendations(ai_response)
        priority_breakdown = self._calculate_priority_breakdown(recommendations)
        summary = ai_response.get("summary", self._generate_summary(recommendations))
        return RecommendationsResponse(
            request_id=request_id,
            recommendations=recommendations,
            summary=summary,
            total_recommendations=len(recommendations),
            priority_breakdown=priority_breakdown,
            processing_metadata={
                "model": settings.openai_model,
                "timestamp": datetime.now().isoformat(),
                "user_role": request.user_role,
                "provider": "openai",
                "api_version": "v1",
            },
        )

