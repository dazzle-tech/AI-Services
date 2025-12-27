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
            request: User role recommendation request with new input structure
            
        Returns:
            Recommendations response from user's specialty perspective
        """
        try:
            request_id = request.request_id or f"role_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Extract user role from practitioner field
            # Format: "Role: NURSE | Specialty: RESIDENT_DOCTOR"
            user_role = self._extract_specialty_from_practitioner(request.practitioner)
            logger.info(f"Processing user role recommendations {request_id} for {user_role}")
            
            # Map new input structure to patient context format expected by AI client
            patient_context_dict = self._map_to_patient_context(request)
            
            # Always use "medical" as recommendation type
            rec_types = [RecommendationType.MEDICAL.value]
            
            logger.info(f"User role: {user_role}")
            logger.info(f"Patient context: {patient_context_dict}")
            logger.info(f"Recommendation type: medical (fixed)")
            
            # Generate role-based recommendations
            logger.info(f"Generating recommendations from {user_role} perspective...")
            ai_response = self.ai_client.generate_role_based_recommendations(
                user_role=user_role,
                patient_context=patient_context_dict,
                recommendation_types=rec_types,
                complaint=request.complain,
                focus_areas=None
            )
            
            # Parse recommendations
            recommendations = self.ai_client.parse_recommendations(ai_response)
            logger.info(f"Generated {len(recommendations)} recommendations from {user_role} perspective")
            
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
                    "user_role": user_role,
                    "recommendation_type": "medical",
                    "provider": "openai",
                    "api_version": "v1"
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing user role recommendations {request.request_id}: {e}")
            raise ValueError(f"User role recommendations failed: {str(e)}")
    
    def _extract_specialty_from_practitioner(self, practitioner: str) -> str:
        """
        Extract specialty from practitioner string.
        Format: "Role: NURSE | Specialty: RESIDENT_DOCTOR"
        Returns specialty in lowercase format suitable for MedicalSpecialty enum.
        """
        try:
            # Extract specialty part
            if "Specialty:" in practitioner:
                specialty_part = practitioner.split("Specialty:")[1].strip()
                # Convert to lowercase and handle common formats
                specialty_lower = specialty_part.lower().replace("_", " ").replace("-", " ").strip()
                
                # Map common specialty formats to enum values
                specialty_mapping = {
                    # ===== Roles =====
                    "resident doctor": "resident doctor",
                    "nurse": "nurse",

                    # ===== Primary Care =====
                    "general": "general",
                    "family medicine": "family medicine",
                    "internal medicine": "internal medicine",
                    "geriatrics": "geriatrics",

                    # ===== Surgery =====
                    "general surgery": "general surgery",
                    "cardiothoracic surgery": "cardiothoracic surgery",
                    "neurosurgery": "neurosurgery",
                    "orthopedic surgery": "orthopedic surgery",
                    "plastic and reconstructive surgery": "plastic and reconstructive surgery",
                    "vascular surgery": "vascular surgery",
                    "urology": "urology",
                    "oral and maxillofacial surgery": "oral and maxillofacial surgery",
                    "trauma surgery": "trauma surgery",
                    "bariatric surgery": "bariatric surgery",
                    "colorectal surgery": "colorectal surgery",
                    "transplant surgery": "transplant surgery",

                    # ===== Medical Specialties =====
                    "cardiology": "cardiology",
                    "endocrinology": "endocrinology",
                    "gastroenterology": "gastroenterology",
                    "hematology": "hematology",
                    "infectious disease": "infectious disease",
                    "nephrology": "nephrology",
                    "neurology": "neurology",
                    "oncology": "oncology",
                    "pulmonology": "pulmonology",
                    "rheumatology": "rheumatology",
                    "dermatology": "dermatology",
                    "allergy and immunology": "allergy and immunology",

                    # ===== ENT / Eyes =====
                    "otolaryngology (ent)": "otolaryngology (ent)",
                    "ophthalmology": "ophthalmology",

                    # ===== Diagnostics =====
                    "pathology": "pathology",
                    "radiology": "radiology",
                    "nuclear medicine": "nuclear medicine",
                    "clinical laboratory medicine": "clinical laboratory medicine",

                    # ===== Rehab & Pain =====
                    "physical medicine and rehabilitation (pm&r)": "physical medicine and rehabilitation (pm&r)",
                    "pain medicine": "pain medicine",
                    "sports medicine": "sports medicine",
                    "sleep medicine": "sleep medicine",

                    # ===== OB / GYN =====
                    "obstetrics and gynecology (ob/gyn)": "obstetrics and gynecology (ob/gyn)",
                    "maternal-fetal medicine": "maternal-fetal medicine",
                    "reproductive endocrinology and infertility": "reproductive endocrinology and infertility",
                    "gynecologic oncology": "gynecologic oncology",

                    # ===== Pediatrics Subspecialties =====
                    "pediatrics": "pediatrics",
                    "pediatric cardiology": "pediatric cardiology",
                    "pediatric endocrinology": "pediatric endocrinology",
                    "pediatric gastroenterology": "pediatric gastroenterology",
                    "pediatric hematology/oncology": "pediatric hematology/oncology",
                    "pediatric nephrology": "pediatric nephrology",
                    "pediatric neurology": "pediatric neurology",
                    "pediatric pulmonology": "pediatric pulmonology",
                    "pediatric infectious disease": "pediatric infectious disease",

                    # ===== Psychiatry =====
                    "psychiatry": "psychiatry",
                    "child and adolescent psychiatry": "child and adolescent psychiatry",
                    "forensic psychiatry": "forensic psychiatry",
                    "geriatric psychiatry": "geriatric psychiatry",

                    # ===== Emergency & Critical =====
                    "emergency medicine": "emergency medicine",
                    "critical care medicine": "critical care medicine",

                    # ===== Public / Other =====
                    "public health medicine": "public health medicine",
                    "occupational medicine": "occupational medicine",
                    "aerospace medicine": "aerospace medicine",
                    "medical genetics": "medical genetics",
                    "hospice and palliative medicine": "hospice and palliative medicine",
                    "lifestyle medicine": "lifestyle medicine",

                    # ===== Anesthesia =====
                    "anesthesiology": "anesthesiology"
                }
                
                # Try exact match first
                if specialty_lower in specialty_mapping:
                    return specialty_mapping[specialty_lower]

                # Then try "contains" match (keeps your previous behavior)
                for key, value in specialty_mapping.items():
                    if key in specialty_lower:
                        return value
                
                # Default to general if no match found
                return "general"
            else:
                # If no specialty found, default to general
                return "general"
        except Exception as e:
            logger.warning(f"Error extracting specialty from practitioner '{practitioner}': {e}")
            return "general"
    
    def _map_to_patient_context(self, request: UserRoleRecommendationRequest) -> Dict[str, Any]:
        """
        Map new input structure to patient context format expected by AI client.
        
        Args:
            request: UserRoleRecommendationRequest with new structure
            
        Returns:
            Dictionary in patient context format
        """
        # Extract allergies from miniSummary
        allergies = request.miniSummary.allergies if request.miniSummary.allergies else []
        
        # Build patient context dictionary
        patient_context = {
            "age": request.visit.patientAge,  # Use patientAge from visit
            "gender": request.patient.gender,
            "diagnosis": request.diagnosis.value,  # Use diagnosis value
            "symptoms": [request.visit.chiefComplaint] if request.visit.chiefComplaint else [],
            "medications": [],  # Not provided in new structure
            "allergies": allergies,
            "comorbidities": [],  # Not provided in new structure
            "vitals": {},  # Not provided in new structure
            "lab_results": {},  # Not provided in new structure
            "clinical_notes": self._build_clinical_notes(request)
        }
        
        return patient_context
    
    def _build_clinical_notes(self, request: UserRoleRecommendationRequest) -> str:
        """Build clinical notes from available information."""
        notes_parts = []
        
        notes_parts.append(f"Patient MRN: {request.patient.mrn}")
        notes_parts.append(f"Patient Name: {request.patient.fullName}")
        notes_parts.append(f"Date of Birth: {request.patient.dob}")
        notes_parts.append(f"Visit ID: {request.visit.visitId}")
        notes_parts.append(f"Visit Type: {request.visit.visitType}")
        notes_parts.append(f"Planned Start Date: {request.visit.plannedStartDate}")
        notes_parts.append(f"Chief Complaint: {request.visit.chiefComplaint}")
        notes_parts.append(f"Complaint: {request.complain}")
        notes_parts.append(f"Diagnosis Type: {request.diagnosis.type}")
        notes_parts.append(f"Diagnosis: {request.diagnosis.value}")
        notes_parts.append(f"Practitioner: {request.practitioner}")
        
        if request.miniSummary.medicalWarnings:
            notes_parts.append(f"Medical Warnings: {request.miniSummary.medicalWarnings}")
        
        return "\n".join(notes_parts)
