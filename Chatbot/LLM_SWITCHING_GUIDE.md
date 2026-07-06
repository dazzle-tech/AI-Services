# Switching from LLaMA to GPT-4o Guide

This guide explains how to use the OpenAI-compatible path with Ollama and `qwen3:1.7b`.

## Quick Start

### 1. Install OpenAI Library

```powershell
pip install openai
```

### 2. Set Environment Variables

Create a `.env` file in the `chatbot` directory (or set environment variables):

```env
# Switch to OpenAI
LLM_PROVIDER=openai

# OpenAI Configuration
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=qwen3:1.7b
OPENAI_SQL_GEN_MODEL=qwen3:1.7b

# Optional: Use different models for different tasks
# OPENAI_MODEL=qwen3:1.7b
# OPENAI_SQL_GEN_MODEL=qwen3:1.7b
```

### 3. Restart Services

Restart all services to pick up the new configuration:

```powershell
# Stop all services (Ctrl+C)
# Then restart:
python runners/main_orchestrator.py
python runners/main_sql_generator.py
python runners/main_formatter.py
python runners/main_validator.py
```

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | Provider: `"ollama"` or `"openai"` |
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `OPENAI_MODEL` | `qwen3:1.7b` | Model for general tasks (chat, formatting, etc.) |
| `OPENAI_SQL_GEN_MODEL` | `qwen3:1.7b` | Model specifically for SQL generation |
| `LLM_MODEL` | `qwen3:1.7b` | Ollama model (when using Ollama) |
| `SQL_GEN_MODEL` | `qwen3:1.7b` | Ollama SQL model (when using Ollama) |

### Recommended Models

**For Best Results (Higher Cost):**
- `OPENAI_MODEL=qwen3:1.7b`
- `OPENAI_SQL_GEN_MODEL=qwen3:1.7b`

**For Cost Savings (Still Good Quality):**
- `OPENAI_MODEL=qwen3:1.7b`
- `OPENAI_SQL_GEN_MODEL=qwen3:1.7b`

**For Maximum Cost Savings:**
- `OPENAI_MODEL=qwen3:1.7b`
- `OPENAI_SQL_GEN_MODEL=qwen3:1.7b`

## What Gets Switched

When you set `LLM_PROVIDER=openai`, all services automatically use OpenAI:

1. **Chat Orchestrator** - Uses GPT-4o for general chat responses
2. **SQL Generator** - Uses GPT-4o for SQL query generation
3. **Formatter** - Uses GPT-4o for result summarization
4. **Intent Detection** - Uses GPT-4o for intent classification
5. **Entity Extraction** - Uses GPT-4o for extracting patient info
6. **Spelling Correction** - Uses GPT-4o for query correction
7. **Scope Detection** - Uses GPT-4o for query scope analysis

## Switching Back to Ollama

To switch back to Ollama:

```env
LLM_PROVIDER=ollama
# Remove or comment out OPENAI_API_KEY
```

## Cost Considerations

**GPT-4o Pricing (as of 2024):**
- Input: $2.50 per 1M tokens
- Output: $10.00 per 1M tokens

**GPT-4o-mini Pricing:**
- Input: $0.15 per 1M tokens
- Output: $0.60 per 1M tokens

**Typical Query:**
- Input: ~500-1000 tokens
- Output: ~200-500 tokens
- Cost per query with GPT-4o: ~$0.01-0.02
- Cost per query with GPT-4o-mini: ~$0.001-0.002

## Benefits of GPT-4o

1. **Better SQL Generation** - More accurate SQL queries, better understanding of "recently", etc.
2. **Better Intent Detection** - More accurate classification
3. **Better Formatting** - More natural language summaries
4. **Better Entity Extraction** - More accurate patient name/ID extraction
5. **Better Spelling Correction** - More accurate corrections

## Testing

After switching, test with:

1. **SQL Generation:**
   ```
   "who was discharged recently"
   "give me all patients with allergies"
   ```

2. **Intent Detection:**
   ```
   "hello" (should be "chat")
   "what is the patient's age" (should be "data")
   ```

3. **Formatting:**
   - Check if summaries are more natural
   - Check if plural queries show all results

## Troubleshooting

### Error: "OpenAI library not installed"
```powershell
pip install openai
```

### Error: "OpenAI API key is required"
- Set `OPENAI_API_KEY` environment variable
- Or add it to `.env` file

### Error: "Rate limit exceeded"
- You've hit OpenAI's rate limit
- Wait a few minutes or upgrade your plan
- Use `qwen3:1.7b` consistently across the OpenAI-compatible and Ollama paths

### Still using Ollama after switching?
- Make sure you restarted all services
- Check that `.env` file is in the `chatbot` directory
- Verify `LLM_PROVIDER=openai` is set correctly

## Architecture

The system uses a unified `LLMClient` that automatically routes to:
- `OllamaClient` when `LLM_PROVIDER=ollama`
- `OpenAIClient` when `LLM_PROVIDER=openai`

All services use `get_llm_client()` which handles the switching automatically.


