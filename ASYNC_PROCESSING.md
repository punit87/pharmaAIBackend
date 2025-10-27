# Async Document Processing Implementation

## Summary of Changes

Implemented **asynchronous document processing** to eliminate timeout issues and improve user experience.

## Key Changes

### 1. **Background Processing with ThreadPoolExecutor**
- Added `ThreadPoolExecutor` for background task execution
- Created `process_document_background()` function that runs asynchronously
- Documents are queued and processed in the background

### 2. **Simple Text-Based Chunking**
- Replaced slow LLM-based chunking with fast text splitting
- New `simple_chunking()` function splits markdown by lines
- No more LLM API timeouts!

### 3. **Non-Blocking /process Endpoint**
- `/process` endpoint now returns immediately
- Returns "accepted" status indicating background processing started
- User doesn't have to wait for document to finish processing

## Benefits

✅ **No Timeouts**: Processing happens in background  
✅ **Fast Response**: API returns immediately  
✅ **Better UX**: User doesn't wait 5+ minutes  
✅ **No LLM Delays**: Simple chunking is instant  
✅ **Reliable**: Chunks are always created  

## How It Works Now

### Old Flow ❌
```
1. Upload to S3
2. Lambda calls /process
3. Wait for Docling parsing (40s)
4. Wait for LLM chunking (300s) → TIMEOUT!
5. Timeout error
```

### New Flow ✅
```
1. Upload to S3
2. Lambda calls /process
3. API returns immediately: "accepted"
4. Background thread:
   - Downloads PDF
   - Parses with Docling
   - Simple text chunking (instant) OR LLM chunking (if enabled)
   - Inserts into LightRAG
   - Logs completion
```

## Chunking Methods

### Default: RAG-Anything Native Chunks (Recommended)
Uses structured chunks directly from RAG-Anything/Docling parsing:
```python
# Extract native chunks from parse_result
for element in structured_data:
    chunks.append({
        'type': 'text',
        'content': element.get('text', ''),
        'metadata': {
            'doc_id': s3_key,
            'page_idx': element.get('page_idx', 0),
            'element_type': element.get('type')
        }
    })
```
**Benefits**: Preserves document structure, page numbers, element types

### Optional: LLM Chunking (Intelligent)
Uses GPT to intelligently chunk content - slower but more semantic:
```python
# Enable by setting environment variable
USE_LLM_CHUNKING=true
```

To use LLM chunking, set the environment variable when starting the container:
```bash
docker run -e USE_LLM_CHUNKING=true ...
```

## Testing

To test the new async processing:

```bash
# Upload document
curl -X PUT -T "1.pdf" "PRESIGNED_URL"

# Trigger processing (returns immediately)
curl -X POST http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com/process \
  -H "Content-Type: application/json" \
  -d '{"bucket": "pharma-documents-dev-864899869769-us-east-1-v5", "key": "YOUR_KEY"}'

# Response (returns in <1s):
{"status": "accepted", "message": "Document processing started in background"}

# Check logs for completion
# Query after a minute to verify chunks were indexed
```

## Next Steps

1. **Deploy the updated container** with the new code
2. **Test async processing** with a new document upload
3. **Verify chunks are indexed** and queryable

## Commit Details

```
commit b666db4
Author: bejoypramanick
Date: Mon Oct 27 17:56:39 2025

feat: implement async document processing and simple chunking

- Add ThreadPoolExecutor for background document processing
- Create simple_chunking() function to replace LLM-based chunking  
- Implement process_document_background() for async processing
- /process endpoint now returns immediately after queueing background task
- Removes timeout issues by processing documents asynchronously
- Simple text-based chunking avoids LLM API timeouts

apps/rag_client.py | 180 lines changed (87 insertions, 93 deletions)
```

