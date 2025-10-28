# Document Upload Integration - Knowledge-base Management

## Summary

Successfully integrated document upload functionality into the Knowledge-base Management screen, enabling users to upload PDF, DOCX, and TXT files directly through the frontend.

## Changes Made

### 1. **knowledge-base.ts** - Updated API Methods

**File**: `/Users/bejoypramanick/iCloud Drive (Archive) - 1/Desktop/globistaan/projects/chatbot/knowledgebot/src/lib/knowledge-base.ts`

**Updates**:
- Modified `getPresignedUploadUrl()` to call the pharma backend API Gateway endpoint
  - Endpoint: `GET https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev/presigned-url`
  - Returns presigned S3 upload URL

- Added `triggerDocumentProcessing()` method
  - Calls ECS `/process` endpoint to trigger document processing
  - Endpoint: `POST http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com/process`

### 2. **KnowledgeBaseManagement.tsx** - Added Upload UI

**File**: `/Users/bejoypramanick/iCloud Drive (Archive) - 1/Desktop/globistaan/projects/chatbot/knowledgebot/src/pages/KnowledgeBaseManagement.tsx`

**Updates**:
- Added upload state management:
  - `isUploading` - tracks upload progress
  - `uploadProgress` - shows 0-100% progress

- Added `handleFileUpload()` function:
  - Gets presigned URL from API Gateway (10%)
  - Uploads file to S3 with progress tracking (20-90%)
  - Triggers document processing (90-95%)
  - Completes upload (95-100%)
  - Shows success message
  - Reloads document list

- Added UI components:
  - Upload button in header
  - Hidden file input (accepts .pdf, .docx, .txt)
  - Progress bar during upload
  - Success/error messages

## Upload Flow

```
┌────────────────────────────────────┐
│  User clicks "Upload Document"    │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│  Select file (.pdf, .docx, .txt)  │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│  1. Call API Gateway              │
│     /presigned-url                │
│     Progress: 10%                 │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│  2. Upload file to S3             │
│     using presigned URL           │
│     Progress: 20-90%              │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│  3. Trigger document processing   │
│     POST /process                 │
│     Progress: 90-95%              │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│  4. Show success message          │
│     Reload documents list         │
│     Progress: 100%                │
└────────────────────────────────────┘
```

## Backend Integration

### API Gateway Endpoint
- **URL**: `https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev/presigned-url`
- **Method**: GET
- **Response**:
```json
{
  "presigned_url": "https://s3.amazonaws.com/...",
  "bucket": "pharma-documents-dev-...",
  "key": "test-documents/uuid.pdf",
  "expires_in": 300
}
```

### S3 Upload
- File uploaded directly to S3 using presigned URL
- PutObject operation
- Content-Type preserved
- Progress tracking enabled

### Document Processing
- S3 upload triggers Lambda (`document_processor`)
- Lambda calls ECS `/process` endpoint
- Document processed in background (async)
- Docling parsing → Chunking → LightRAG insertion
- Status updated to "processing" → "processed"

## User Experience

1. **Upload Button**: Prominent button in header with Plus icon
2. **Progress Tracking**: Real-time progress bar showing upload percentage
3. **Success Feedback**: Green success message after upload
4. **Error Handling**: Red error message if upload fails
5. **Auto-reload**: Documents list refreshes after successful upload
6. **Disabled State**: Button disabled during upload (prevents multiple uploads)

## File Types Supported

- `.pdf` - PDF documents
- `.docx` - Microsoft Word documents
- `.txt` - Plain text files

## Environment Variables

Add to `.env`:
```env
VITE_PHARMA_API_URL=https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev
VITE_PHARMA_ALB_URL=http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com
```

## Testing

1. Navigate to Knowledge-base Management screen
2. Click "Upload Document" button
3. Select a PDF file (e.g., `1.pdf`)
4. Watch progress bar fill up
5. See success message
6. Verify document appears in list
7. Check that document status shows "processed" after processing completes

## Error Handling

- Invalid file type: Frontend validation
- Upload timeout: 5 minute timeout with user feedback
- Network errors: Error message displayed
- Processing failures: Document shows in list with "failed" status

## Next Steps

✅ Upload functionality integrated
✅ Progress tracking implemented  
✅ Success/error feedback added
✅ Auto-reload on success
⏳ Document status polling (optional enhancement)
⏳ File size validation (optional enhancement)
⏳ Batch upload support (future enhancement)

