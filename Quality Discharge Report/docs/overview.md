# Discharge QA Service Overview

## Architecture

The Discharge QA Service is a microservice that performs quality assurance on clinical discharge reports using AI-powered analysis.

## Components

### 1. API Layer (`src/api/`)
- RESTful endpoints for QA operations
- Request/response validation
- Error handling

### 2. Core Layer (`src/core/`)
- **prompt_runner.py**: Loads and executes prompts using OpenAI
- **openai_client.py**: Wraps OpenAI API calls
- **response_validator.py**: Validates JSON output against schema

### 3. Service Layer (`src/services/discharge_qa/`)
- **service.py**: Main orchestrator for QA flow
- **parser.py**: Parses text reports into structured format
- **normalizer.py**: Normalizes medications, vitals, sections
- **conflict_resolver.py**: Resolves conflicts between documents
- **scoring.py**: Calculates overall quality score
- **types.py**: Type definitions and enums

### 4. Domain Layer (`src/domain/`)
- **entities.py**: Core domain models
- **rules.py**: Quality rule loaders

### 5. Security Layer (`src/security/`)
- **anonymization_check.py**: PHI detection and prevention

## Workflow

1. Receive QA request with discharge report and supporting documents
2. Parse and normalize the discharge report
3. Load quality rules and template
4. Execute AI prompt with all inputs
5. Validate and parse AI response
6. Post-process results (scoring, conflict resolution)
7. Return structured JSON output

## Quality Categories

- **Completeness**: Required sections and fields present
- **Consistency**: Alignment with patient record and clinical docs
- **Safety**: High-risk issues (medication errors, missing warnings)
- **Structure**: Formatting, organization, template compliance

