# Chunking Method Selection

## Overview

You can now control the chunking method **per request** by passing the `use_llm_chunking` parameter in your `/process` endpoint calls.

## API Usage

### Basic Request (Default: Fast Native Chunking)

```bash
curl -X POST https://your-api-url/process \
  -H "Content-Type: application/json" \
  -d '{
    "bucket": "your-bucket-name",
    "key": "uploads/document.pdf"
  }'
```

**Result**: Uses native Docling chunking (fast, default)

### Request with LLM Chunking

```bash
curl -X POST https://your-api-url/process \
  -H "Content-Type: application/json" \
  -d '{
    "bucket": "your-bucket-name",
    "key": "uploads/document.pdf",
    "use_llm_chunking": true
  }'
```

**Result**: Uses GPT-4o-mini for semantic chunking (slower but more intelligent)

## Parameter Values

The `use_llm_chunking` parameter accepts:

- `true` / `false` (boolean)
- `"true"` / `"false"` (string)
- `"1"` / `"0"` (string)
- `"yes"` / `"no"` (string)

**Default**: `false` (if not specified)

## Response Format

```json
{
  "status": "accepted",
  "message": "Document processing started in background",
  "bucket": "your-bucket-name",
  "key": "uploads/document.pdf",
  "use_llm_chunking": false
}
```

## Chunking Methods

### 1. Native Docling Chunking (Default)

**When**: `use_llm_chunking: false` or not specified

**How it works**:
- Uses Docling's structured output directly
- Extracts text from each element
- Fast processing (seconds)
- Preserves document structure
- Includes page numbers and element types

**Best for**:
- General documents
- Fast processing needed
- Structured documents (PDFs, images)

### 2. LLM Chunking (Optional)

**When**: `use_llm_chunking: true`

**How it works**:
- Converts document to markdown
- Uses GPT-4o-mini to intelligently chunk content
- Semantic understanding of text
- Creates cohesive chunks
- Slower processing (minutes)

**Best for**:
- Complex documents
- Research papers
- Need semantic coherence
- When quality > speed

## Examples

### Example 1: Fast Processing

```bash
# Process with default native chunking
curl -X POST https://api.example.com/process \
  -H "Content-Type: application/json" \
  -d '{
    "bucket": "my-bucket",
    "key": "uploads/report.pdf"
  }'
```

Response:
```json
{
  "status": "accepted",
  "bucket": "my-bucket",
  "key": "uploads/report.pdf",
  "use_llm_chunking": false
}
```

### Example 2: LLM Chunking

```bash
# Process with LLM chunking
curl -X POST https://api.example.com/process \
  -H "Content-Type: application/json" \
  -d '{
    "bucket": "my-bucket",
    "key": "uploads/research-paper.pdf",
    "use_llm_chunking": true
  }'
```

Response:
```json
{
  "status": "accepted",
  "bucket": "my-bucket",
  "key": "uploads/research-paper.pdf",
  "use_llm_chunking": true
}
```

## Log Output

The logs will show which chunking method is being used:

### Native Chunking Logs
```
📄 [BG_PROCESS] Use LLM Chunking: False
🔍 [BG_PROCESS] Step 4: Extracting chunks...
📦 [BG_PROCESS] Using native Docling chunks (fast mode)...
✅ [BG_PROCESS] Native chunking SUCCESS: Created 42 chunks
```

### LLM Chunking Logs
```
📄 [BG_PROCESS] Use LLM Chunking: True
🔍 [BG_PROCESS] Step 4: Extracting chunks...
🔪 [BG_PROCESS] USE_LLM_CHUNKING enabled - using LLM chunking...
🔪 [BG_PROCESS] Calling custom_llm_chunking...
✅ [BG_PROCESS] LLM chunking SUCCESS: Created 38 chunks
```

## When to Use Each Method

| Use Native Chunking (Default) | Use LLM Chunking |
|------------------------------|------------------|
| ✅ Fast processing needed | ✅ Semantic coherence important |
| ✅ Simple documents | ✅ Complex research papers |
| ✅ Standard PDFs/images | ✅ Need intelligent chunking |
| ✅ Production workloads | ✅ Can afford slower processing |
| ✅ High throughput | ✅ Quality over speed |

## Migration

If you were using the environment variable `USE_LLM_CHUNKING`, you now need to pass it per request:

**Old way** (environment variable):
```bash
# In Docker/ECS task definition
USE_LLM_CHUNKING=true
```

**New way** (request parameter):
```bash
curl -X POST ... \
  -d '{"bucket": "...", "key": "...", "use_llm_chunking": true}'
```

This allows **per-request control** instead of a global setting!

