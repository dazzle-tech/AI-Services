"""Service layer for clinical recommendations generation."""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.models.schemas import (
    RecommendationRequest,
    RecommendationsResponse,
    ClinicalRecommendation,
    RecommendationPriority,
    SpecialtyConsultationRequest,
    SpecialtyConsultationResponse,
    UserRoleRecommendationRequest,
    MedicalSpecialty,
    RecommendationType
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
            
            # Always use "medical" as recommendation type
            rec_types = [RecommendationType.MEDICAL.value]
            
            # Log input data (for debugging)
            logger.info(f"Patient context: {patient_context_dict}")
            logger.info(f"Recommendation type: medical (fixed)")
            
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
                    "recommendation_type": "medical",
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
    
    def process_specialty_consultation(self, request: SpecialtyConsultationRequest) -> SpecialtyConsultationResponse:
        """
        Process specialty-based consultation request.
        Returns concise summary containing all recommendations for the selected specialty.
        
        Args:
            request: Specialty consultation request
            
        Returns:
            Specialty consultation response with concise summary
        """
        try:
            request_id = request.request_id or f"spec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing specialty consultation request {request_id} for {request.specialty.value}")
            
            # Build patient context (use provided if available, otherwise empty)
            patient_context_dict = {}
            if request.patient_context:
                patient_context_dict = request.patient_context.dict()
            # If no patient context provided, use empty dict - API will return general specialty recommendations
            
            # Generate specialty-specific recommendations
            logger.info(f"Generating {request.specialty.value} specialty recommendations...")
            ai_response = self.ai_client.generate_specialty_recommendations(
                specialty=request.specialty.value,
                patient_context=patient_context_dict,
                complaint=request.complaint
            )
            
            # Parse recommendations to build comprehensive summary
            recommendations = self.ai_client.parse_recommendations(ai_response)
            logger.info(f"Generated {len(recommendations)} {request.specialty.value} recommendations")
            
            # Build concise summary that includes all recommendations
            summary = self._build_concise_summary(recommendations, request.specialty.value, ai_response.get("summary"))
            
            return SpecialtyConsultationResponse(
                request_id=request_id,
                summary=summary,
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "specialty": request.specialty.value,
                    "provider": "openai",
                    "api_version": "v1"
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing specialty consultation {request.request_id}: {e}")
            raise ValueError(f"Specialty consultation failed: {str(e)}")
    
    def _build_concise_summary(self, recommendations: List[ClinicalRecommendation], specialty: str, ai_summary: Optional[str] = None) -> str:
        """Build a direct, concise summary containing all recommendations."""
        if not recommendations:
            return f"{specialty}: No recommendations."
        
        # Extract key items from recommendations
        diagnostic_items = []
        treatment_items = []
        monitoring_items = []
        
        for rec in recommendations:
            title_lower = rec.title.lower()
            
            # Extract from actionable steps
            if rec.actionable_steps:
                if any(word in title_lower for word in ["diagnostic", "test", "workup", "evaluation", "assessment", "examination"]):
                    # Extract test names from steps
                    for step in rec.actionable_steps:
                        # Extract key terms (tests, procedures)
                        words = step.split()
                        for i, word in enumerate(words):
                            if word.lower() in ["ecg", "ekg", "echo", "echocardiogram", "stress", "test", "mri", "ct", "scan", "x-ray", "blood"]:
                                diagnostic_items.append(step)
                                break
                        if len(diagnostic_items) >= 4:
                            break
                
                elif any(word in title_lower for word in ["treatment", "therapy", "protocol", "medication", "prescribe", "intervention"]):
                    for step in rec.actionable_steps[:3]:
                        treatment_items.append(step)
                
                elif any(word in title_lower for word in ["monitoring", "follow-up", "followup", "follow"]):
                    for step in rec.actionable_steps[:2]:
                        monitoring_items.append(step)
            
            # Also extract from description if steps are empty
            if not rec.actionable_steps and rec.description:
                desc_lower = rec.description.lower()
                if any(word in desc_lower for word in ["ecg", "echo", "test", "diagnostic"]):
                    # Extract test names
                    if "ecg" in desc_lower or "ekg" in desc_lower:
                        diagnostic_items.append("ECG")
                    if "echo" in desc_lower or "echocardiogram" in desc_lower:
                        diagnostic_items.append("Echocardiogram")
                elif any(word in desc_lower for word in ["medication", "treatment", "therapy"]):
                    treatment_items.append(rec.title)
                elif any(word in desc_lower for word in ["monitoring", "follow-up"]):
                    monitoring_items.append(rec.title)
        
        # Build direct summary
        parts = []
        
        if diagnostic_items:
            # Clean and deduplicate
            diag_clean = list(dict.fromkeys([item.split(':')[-1].strip() if ':' in item else item.strip() for item in diagnostic_items[:5]]))
            parts.append(f"Diagnostic: {', '.join(diag_clean)}")
        
        if treatment_items:
            treat_clean = list(dict.fromkeys([item.split(':')[-1].strip() if ':' in item else item.strip() for item in treatment_items[:4]]))
            parts.append(f"Treatment: {', '.join(treat_clean)}")
        
        if monitoring_items:
            mon_clean = list(dict.fromkeys([item.split(':')[-1].strip() if ':' in item else item.strip() for item in monitoring_items[:3]]))
            parts.append(f"Monitoring: {', '.join(mon_clean)}")
        
        # If we have a good AI summary that's already direct, use it
        if ai_summary:
            # Check if AI summary follows direct format (has "Diagnostic:", "Treatment:", etc.)
            if "Diagnostic:" in ai_summary or "diagnostic" in ai_summary.lower():
                # Clean up AI summary - remove extra words
                cleaned = ai_summary
                # Remove common filler words
                for word in ["typically", "usually", "generally", "often", "commonly", "may include", "such as", "including"]:
                    cleaned = cleaned.replace(word, "")
                # If still too long, extract key parts
                if len(cleaned) > 300:
                    # Try to extract just the lists
                    if "Diagnostic:" in cleaned:
                        diag_part = cleaned.split("Diagnostic:")[1].split("Treatment:")[0] if "Treatment:" in cleaned else cleaned.split("Diagnostic:")[1][:100]
                        treat_part = cleaned.split("Treatment:")[1].split("Monitoring:")[0] if "Monitoring:" in cleaned else (cleaned.split("Treatment:")[1][:100] if "Treatment:" in cleaned else "")
                        mon_part = cleaned.split("Monitoring:")[1][:100] if "Monitoring:" in cleaned else ""
                        parts = []
                        if diag_part.strip():
                            parts.append(f"Diagnostic: {diag_part.strip()}")
                        if treat_part.strip():
                            parts.append(f"Treatment: {treat_part.strip()}")
                        if mon_part.strip():
                            parts.append(f"Monitoring: {mon_part.strip()}")
                        return ". ".join(parts)
                return cleaned.strip()
        
        # Build from extracted items
        if parts:
            return ". ".join(parts)
        
        # Fallback: use AI summary if available, otherwise build from titles
        if ai_summary:
            return ai_summary[:300]
        
        # Last resort: use recommendation titles
        titles = [rec.title for rec in recommendations[:3]]
        return f"{specialty}: {', '.join(titles)}"
    
    def process_user_role_recommendations(self, request: UserRoleRecommendationRequest) -> RecommendationsResponse:
        """
        Process user role-based recommendations.
        Returns recommendations from the perspective of the user's specialty.
        
        Args:
            request: User role recommendation request
            
        Returns:
            Recommendations response from user's specialty perspective
        """
        try:
            request_id = request.request_id or f"role_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing user role recommendations {request_id} for {request.user_role.value}")
            
            # Convert patient context to dict
            patient_context_dict = request.patient_context.dict()
            
            # Always use "medical" as recommendation type
            rec_types = [RecommendationType.MEDICAL.value]
            
            logger.info(f"User role: {request.user_role.value}")
            logger.info(f"Patient context: {patient_context_dict}")
            logger.info(f"Recommendation type: medical (fixed)")
            
            # Generate role-based recommendations
            logger.info(f"Generating recommendations from {request.user_role.value} perspective...")
            ai_response = self.ai_client.generate_role_based_recommendations(
                user_role=request.user_role.value,
                patient_context=patient_context_dict,
                recommendation_types=rec_types,
                complaint=request.complaint,
                focus_areas=request.focus_areas
            )
            
            # Parse recommendations
            recommendations = self.ai_client.parse_recommendations(ai_response)
            logger.info(f"Generated {len(recommendations)} recommendations from {request.user_role.value} perspective")
            
            # Build response
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
                    "user_role": request.user_role.value,
                    "recommendation_type": "medical",
                    "provider": "openai",
                    "api_version": "v1"
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing user role recommendations {request.request_id}: {e}")
            raise ValueError(f"User role recommendations failed: {str(e)}")

