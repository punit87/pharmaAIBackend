# Frontend Integration Summary

## ✅ Integration Complete

The knowledgebot frontend has been successfully integrated with the pharma RAG backend query endpoint.

## Changes Made

### 1. **chatbot-api.ts** - Added RAG Query Method

**File**: `/Users/bejoypramanick/iCloud Drive (Archive) - 1/Desktop/globistaan/projects/chatbot/knowledgebot/src/lib/chatbot-api.ts`

**Added Method**:
```typescript
async queryRAG(query: string, mode: 'hybrid' | 'naive' | 'local' = 'hybrid'): Promise<ChatResponse> {
  const ragEndpoint = import.meta.env.VITE_RAG_API_URL || 'http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com';
  
  const response = await axios.post(`${ragEndpoint}/query`, {
    query,
    mode
  });

  return {
    response: response.data.answer,
    session_id: '',
    timestamp: new Date().toISOString(),
    sources: response.data.sources || []
  };
}
```

### 2. **Chatbot.tsx** - Added Toggle & Handler

**File**: `/Users/bejoypramanick/iCloud Drive (Archive) - 1/Desktop/globistaan/projects/chatbot/knowledgebot/src/pages/Chatbot.tsx`

**Changes**:
1. Added `useRAGQuery` state toggle
2. Updated `handleSendMessage()` to call RAG endpoint when enabled
3. Added UI toggle button in header (✓ RAG / ○ WS)

## How to Use

### In the Frontend:

1. **Default Mode**: RAG Query (enabled by default)
2. **Toggle**: Click the "✓ RAG" or "○ WS" button in the header
3. **Query**: Type your question and press Enter

### Query Endpoints:

- **RAG Mode**: `http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com/query`
- **WebSocket Mode**: Original chat functionality

### Configuration:

Add to `.env`:
```env
VITE_RAG_API_URL=http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com
```

## API Request Format

```json
POST /query
{
  "query": "What color is vermilion?",
  "mode": "hybrid"
}
```

## API Response Format

```json
{
  "query": "What color is vermilion?",
  "answer": "Vermilion is a shade of red...",
  "sources": [...],
  "confidence": 0.95,
  "mode": "hybrid",
  "status": "completed",
  "timing": {
    "query_duration": 1.193,
    "parse_duration": 0.0,
    "total_duration": 1.194
  }
}
```

## Features

✅ **Dual Mode Support** - Toggle between RAG and WebSocket  
✅ **Default RAG Mode** - Fast, reliable queries  
✅ **Source Display** - Shows document sources  
✅ **Error Handling** - Graceful fallback on errors  
✅ **Visual Toggle** - Easy mode switching  
✅ **Document Visualization** - Works with existing UI components  

## Testing Steps

1. Open the knowledgebot frontend
2. Verify "✓ RAG" button is shown in header (green)
3. Type: "What color is vermilion a shade of?"
4. Press Enter
5. Receive answer with sources
6. Toggle to "○ WS" to use WebSocket mode

## Next Steps

1. **Configure Environment**:
   - Add `VITE_RAG_API_URL` to environment variables
   - Or update default in `chatbot-api.ts`

2. **Build & Deploy**:
   ```bash
   npm run build
   # Deploy to your hosting platform
   ```

3. **Test Both Modes**:
   - Test RAG mode queries
   - Test WebSocket mode
   - Verify toggle works

## Commit History

```
e2b85d4 - feat: integrate RAG query endpoint from pharma backend
```

## Files Modified

1. `src/lib/chatbot-api.ts` - Added queryRAG() method
2. `src/pages/Chatbot.tsx` - Added toggle & updated handler
3. `RAG_INTEGRATION.md` - Added documentation

## Backend Endpoints Available

- ✅ `POST /query` - RAG queries (integrated)
- ✅ `POST /process` - Document processing
- ✅ `GET /health` - Health check
- ✅ `POST /query_multimodal` - Multimodal queries

The frontend is now ready to query the RAG system!

