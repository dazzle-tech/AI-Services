"""Validation helpers for structured identity extraction."""

from __future__ import annotations

from datetime import date

from app.models.schemas import IdentityIssue, IdentityValidation, PatientIdentity


def validate_identity(
    identity: PatientIdentity,
    *,
    mrz_present: bool,
    mrz_valid: bool | None,
) -> IdentityValidation:
    errors: list[IdentityIssue] = []
    warnings: list[IdentityIssue] = []

    if identity.date_of_birth:
        try:
            dob = date.fromisoformat(identity.date_of_birth)
            if dob > date.today():
                errors.append(
                    IdentityIssue(
                        field="date_of_birth",
                        code="FUTURE_DATE",
                        message="Date of birth cannot be in the future.",
                    )
                )
        except ValueError:
            errors.append(
                IdentityIssue(
                    field="date_of_birth",
                    code="INVALID_DATE",
                    message="Date of birth must be in ISO format YYYY-MM-DD.",
                )
            )

    if identity.document_number:
        compact = "".join(ch for ch in identity.document_number.upper() if ch.isalnum())
        if len(compact) < 5:
            warnings.append(
                IdentityIssue(
                    field="document_number",
                    code="SHORT_DOCUMENT_NUMBER",
                    message="Document number looks shorter than expected; verify OCR output.",
                )
            )

    if identity.nationality:
        compact_nationality = "".join(ch for ch in identity.nationality.upper() if ch.isalpha())
        if len(compact_nationality) not in {3}:
            warnings.append(
                IdentityIssue(
                    field="nationality",
                    code="NON_STANDARD_NATIONALITY",
                    message="Nationality is not a 3-letter code; verify the extracted value.",
                )
            )

    if mrz_present and mrz_valid is False:
        warnings.append(
            IdentityIssue(
                field="document_number",
                code="MRZ_CHECK_FAILED",
                message="MRZ check digits did not validate; verify extracted identity fields.",
            )
        )

    return IdentityValidation(
        ok=not errors,
        errors=errors,
        warnings=warnings,
    )
