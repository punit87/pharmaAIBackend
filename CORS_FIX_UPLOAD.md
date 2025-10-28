# CORS Fix for Document Upload

## Problem

Frontend was getting CORS error when trying to upload documents:
```
Request URL: https://a1kn0j91k8.execute-api.ap-south-1.amazonaws.com/prod/upload-url
CORS error
```

**Root Cause**: Frontend was calling the old chatbot API Gateway instead of the pharma backend API Gateway.

## Solution

### 1. Updated `aws-config.ts`
Added pharma backend API Gateway endpoint:
```typescript
endpoints: {
  // ... existing endpoints
  pharmaApiGateway: 'https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev',
}
```

### 2. Updated `KnowledgeBaseManagement.tsx`
Changed to use pharma backend:
```typescript
const knowledgeBaseManager = new KnowledgeBaseManager(AWS_CONFIG.endpoints.pharmaApiGateway);
```

### 3. Updated `knowledge-base.ts`
- Fixed `getPresignedUploadUrl()` to use `this.apiBaseUrl` parameter
- Fixed `triggerDocumentProcessing()` to use environment variable for ALB URL
- Added `use_llm_chunking: false` parameter for faster processing

## Correct API Endpoints

### API Gateway (presigned URL)
- **URL**: `https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev/presigned-url`
- **Method**: GET
- **CORS**: ✅ Configured (Access-Control-Allow-Origin: *)

### ALB (document processing)
- **URL**: `http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com/process`
- **Method**: POST
- **CORS**: ✅ Configured (via flask-cors)

## Files Changed

1. `/knowledgebot/src/lib/aws-config.ts`
   - Added `pharmaApiGateway` endpoint

2. `/knowledgebot/src/pages/KnowledgeBaseManagement.tsx`
   - Changed to use `AWS_CONFIG.endpoints.pharmaApiGateway`

3. `/knowledgebot/src/lib/knowledge-base.ts`
   - Use configurable API URL instead of hardcoded
   - Added `use_llm_chunking: false` parameter

## Testing

1. Navigate to Knowledge-base Management
2. Click "Upload Document"
3. Select a PDF file
4. Should not get CORS error
5. Upload should complete successfully
6. Document should appear in list

## Environment Variables

Optional - add to `.env`:
```
VITE_PHARMA_API_URL=https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev
VITE_PHARMA_ALB_URL=http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com
```

If not set, defaults are used.

