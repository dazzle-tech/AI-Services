#!/bin/bash

# Validate QA output JSON against schema

SCHEMA_FILE="docs/schemas/discharge_qa.schema.json"
OUTPUT_FILE="${1:-qa_output.json}"

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "Error: Schema file not found: $SCHEMA_FILE"
    exit 1
fi

if [ ! -f "$OUTPUT_FILE" ]; then
    echo "Error: Output file not found: $OUTPUT_FILE"
    exit 1
fi

# Check if jsonschema is installed
if ! command -v jsonschema &> /dev/null; then
    echo "Installing jsonschema..."
    pip install jsonschema
fi

# Validate JSON
echo "Validating $OUTPUT_FILE against $SCHEMA_FILE..."
python -c "
import json
import jsonschema
import sys

with open('$SCHEMA_FILE', 'r') as f:
    schema = json.load(f)

with open('$OUTPUT_FILE', 'r') as f:
    data = json.load(f)

try:
    jsonschema.validate(instance=data, schema=schema)
    print('✓ Validation passed!')
    sys.exit(0)
except jsonschema.ValidationError as e:
    print('✗ Validation failed:')
    print(e.message)
    sys.exit(1)
"

