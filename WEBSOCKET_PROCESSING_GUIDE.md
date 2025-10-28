# WebSocket-Based Document Processing

## Overview
Document processing now uses **WebSocket API** instead of REST API to avoid the 30-second timeout limitation. WebSocket APIs have **no timeout** and can maintain persistent connections.

## Architecture

### Flow:
1. **Frontend** uploads file to S3 (via presigned URL)
2. **Frontend** sends WebSocket message: `{"action": "process_document", "document_key": "...", "bucket": "...", "document_name": "..."}`
3. **WebSocket Lambda** receives message via `$default` route
4. **WebSocket Lambda** sends real-time progress updates:
   - 10%: "Starting document processing..."
   - 20%: "Connecting to ECS processing service..."
   - 40%: "Sending document to processing engine..."
   - 100%: "Document processing completed successfully!"
5. **Frontend** displays progress updates in real-time
6. **Processing completes** - no timeout issues!

## Progress Stages

| Progress | Status | Message |
|----------|--------|---------|
| 10% | starting | Starting document processing... |
| 20% | triggering | Connecting to ECS processing service... |
| 40% | processing | Sending document to processing engine... |
| 100% | complete | Document processing completed successfully! |

## Frontend Integration

### WebSocket Message Format
```javascript
// Send processing request via WebSocket
websocket.send(JSON.stringify({
  action: 'process_document',
  document_key: 'test-documents/uuid_filename.pdf',
  bucket: 'pharma-rag-infrastructure-dev-stora-documentbucket-eayzi8vho3hd',
  document_name: 'filename.pdf'
}));

// Receive progress updates
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.action === 'progressUpdate') {
    console.log(`${data.data.progress}% - ${data.message}`);
    // Update UI progress bar and status text
  }
};
```

## WebSocket Endpoint

- **WebSocket URL**: `wss://6dkgg5u5s7.execute-api.us-east-1.amazonaws.com/dev`
- **Action**: `process_document`
- **Connection**: Persistent (no timeout)

## Benefits

✅ **No 30-second timeout** - WebSocket has unlimited duration  
✅ **Real-time progress updates** - See processing stages live  
✅ **Persistent connection** - One connection for all operations  
✅ **Event-driven** - Frontend receives updates as they happen

## Backend Lambda

- **Function**: `pharma-websocket-message-dev`
- **Timeout**: 300 seconds (5 minutes)
- **Memory**: 512 MB
- **Handles**: WebSocket messages including `process_document` action

