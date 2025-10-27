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
   - Calls rag.parse_document() → returns Docling structured output
   - Extracts chunks from RAG-Anything's structured data
   - Calls rag.insert_content_list() → inserts into LightRAG
   - Logs completion
```

## How It Works

### RAG-Anything's Two-Step Process

**Step 1: Parse with RAG-Anything/Docling**
```python
parse_result = run_async(rag.parse_document(temp_file_path, parse_method='ocr'))
```

**Step 2: Extract and Insert Chunks**
```python
# Extract chunks from Docling's structured output
for element in structured_data:
    content_list.append({
        'type': 'text',
        'text': element.get('text', ''),
        'metadata': {
            'doc_id': s3_key,
            'page_idx': element.get('page_idx', 0),
            'element_type': element.get('type', 'text')
        }
    })

# Insert into RAG-Anything
run_async(rag.insert_content_list(content_list, doc_id=s3_key))
```

**What RAG-Anything Does**:
1. ✅ `parse_document()` - Parses with Docling (OCR, tables, text extraction)
2. ✅ Returns structured elements (already chunked by Docling!)
3. ✅ `insert_content_list()` - Inserts chunks into LightRAG's vector store

**RAG-Anything doesn't have an `insert_document()` method** - use `parse_document()` + `insert_content_list()`

The chunking is handled natively by **Docling's structured output** - no need for manual chunking!

### Chunking Options

**Default: Native Docling Chunking (Fast)** ✅
- Uses Docling's structured elements directly
- Fast and preserves document structure
- Page numbers and element types included

**Optional: LLM Chunking (Slow but Semantic)**
- Enable by setting `USE_LLM_CHUNKING=true`
- Uses GPT-4o-mini to intelligently chunk content
- More semantic but takes longer
- Set environment variable in container/task definition

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

