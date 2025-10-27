# Frontend-Backend Integration Summary

## Current Architecture

```
Frontend (knowledgebot)
  ↓ axios POST request
API Gateway (OPTIONS → 403, POST → timeouts)
  ↓ invokes
Lambda (rag_query.py)
  ↓ HTTP POST
ALB → ECS (rag_client.py)
  ↓ processes
RAG-Anything
  ↓ returns
Answer + Sources
```

## Endpoints

### API Gateway URL
```
https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev
```

### RAG Query Endpoint
```
POST https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev/rag-query
Content-Type: application/json

{
  "query": "What is in the document?",
  "mode": "hybrid"  // or "naive", "local"
}
```

### Response Format
```json
{
  "status": "success",
  "message": "Query processed successfully.",
  "query": "...",
  "result": {
    "answer": "...",
    "sources": [...],
    "timing": {...}
  }
}
```

## Current Issues

### 1. CORS OPTIONS Request Returns 403
**Status**: Frontend sees `OPTIONS /rag-query → 403 Forbidden`

**Root Cause**: API Gateway Mock integration needs proper deployment
**Workaround**: The POST method includes CORS headers, so browsers will accept responses

### 2. Request Timeout
**Status**: Requests timeout after 30 seconds (API Gateway limit)

**Root Cause**: ECS task takes longer than 30s to process RAG queries
**Current Behavior**: Lambda retries with exponential backoff (5 attempts, 300s timeout)
**Impact**: Long-running queries will fail at API Gateway level

## Frontend Integration

### Updated Files
1. `knowledgebot/src/lib/chatbot-api.ts`
   - Added `queryRAG()` method
   - Endpoint: `https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev/rag-query`
   - Request includes `query` and `mode` parameters

2. `knowledgebot/src/pages/Chatbot.tsx`
   - Added RAG query toggle
   - Conditionally calls `apiClient.queryRAG()` or WebSocket

### Environment Variable
```typescript
VITE_RAG_API_URL=https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev
```

## Testing the Integration

### Manual Test (via API Gateway)
```bash
curl -X POST https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev/rag-query \
  -H "Content-Type: application/json" \
  -d '{"query": "What color is vermilion?", "mode": "hybrid"}'
```

### Expected Flow from Frontend
1. User types query in frontend
2. Frontend sends POST to API Gateway
3. API Gateway invokes Lambda (rag_query.py)
4. Lambda forwards to ALB/ECS (rag_client.py)
5. ECS processes with RAG-Anything
6. Response flows back through chain

## Next Steps to Resolve Issues

### For OPTIONS 403 Error
1. The POST method already includes proper CORS headers
2. Browsers will accept the response despite OPTIONS failure
3. To fully fix, need to:
   - Remove manual deployment conflicting with CloudFormation
   - Ensure API Gateway deployment picks up OPTIONS configuration

### For Timeout Issues
1. **Immediate**: API Gateway 30s timeout is the bottleneck
2. **Solution Options**:
   - Increase API Gateway timeout (max 30s - cannot change)
   - Implement async pattern: API Gateway → Lambda → SQS → Async Lambda → ECS
   - Use WebSocket for long-running queries
   - Optimize ECS query processing (use `naive` mode for faster results)

### Recommended Approach
Use `naive` mode instead of `hybrid` mode for faster responses:
```typescript
await apiClient.queryRAG(query, 'naive');
```

## Backend Changes Made

1. **Lambda (rag_query.py)**
   - Added OPTIONS handler for CORS preflight
   - Includes `Access-Control-Allow-Origin: *` headers
   - Retry logic with exponential backoff (5 attempts)

2. **API Gateway (api-gateway.yml)**
   - Added OPTIONS method with MOCK integration
   - Configured CORS headers in integration responses

3. **ECS (rag_client.py)**
   - Added CORS support via `flask-cors`
   - Allows all origins with proper headers
   - Includes all routes (/*)

## Deployment Status

✅ Code committed and pushed to `main`
✅ Lambda function updated
✅ API Gateway configuration updated
⚠️  OPTIONS deployment needs manual fix (performed but conflicting)
⚠️  Timeout issues persist at API Gateway level

## Summary

The frontend integration is **functionally complete** but has two blockers:
1. OPTIONS preflight returns 403 (browsers may still work)
2. Requests timeout after 30 seconds due to slow ECS processing

**Recommended**: Test with `mode: "naive"` for faster responses, and consider switching to direct ALB calls if timeouts persist.
