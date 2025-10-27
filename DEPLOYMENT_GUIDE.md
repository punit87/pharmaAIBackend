# Deployment and Testing Guide

## 🚀 Step 1: Force ECS Service Update

Update the ECS service to use the latest Docker image:

```bash
aws ecs update-service \
    --cluster pharma-rag-cluster \
    --service pharma-raganything-async-service \
    --force-new-deployment \
    --region us-east-1
```

Wait for the service to stabilize (2-3 minutes):

```bash
aws ecs describe-services \
    --cluster pharma-rag-cluster \
    --services pharma-raganything-async-service \
    --region us-east-1 \
    --query 'services[0].deployments[]' \
    --output table
```

## 🗑️ Step 2: Clear EFS Data (Optional but Recommended)

### Option A: Clear via ECS Exec (If Enabled)

1. Enable ECS Exec on the service:
```bash
aws ecs update-service \
    --cluster pharma-rag-cluster \
    --service pharma-raganything-async-service \
    --enable-execute-command \
    --region us-east-1
```

2. Get the task ARN:
```bash
TASK_ARN=$(aws ecs list-tasks --cluster pharma-rag-cluster --query 'taskArns[0]' --output text --region us-east-1)
echo $TASK_ARN
```

3. Connect to the task:
```bash
aws ecs execute-command \
    --cluster pharma-rag-cluster \
    --task $TASK_ARN \
    --container pharma-raganything-async \
    --interactive \
    --command "/bin/bash"
```

4. Once inside the container, clear EFS:
```bash
rm -rf /rag-output/*
ls -la /rag-output/
exit
```

### Option B: Clear via AWS Console

1. Go to **EFS Console**
2. Find your EFS file system
3. Use AWS Systems Manager Session Manager to mount and clear

## ✅ Step 3: Verify Deployment

Check that the new task is running:

```bash
aws ecs list-tasks \
    --cluster pharma-rag-cluster \
    --service-name pharma-raganything-async-service \
    --region us-east-1 \
    --desired-status RUNNING
```

Check CloudWatch logs:

```bash
aws logs tail /aws/ecs/pharma-raganything-async --follow --region us-east-1
```

## 🧪 Step 4: Test the Endpoints

### 1. Test Health Endpoint

```bash
curl -X GET https://<your-api-gateway-url>/health
```

Expected response:
```json
{
  "status": "healthy",
  "rag_initialized": true,
  "uptime": 123
}
```

### 2. Get Presigned URL

```bash
curl -X POST https://<your-api-gateway-url>/presigned-url \
  -H "Content-Type: application/json" \
  -d '{"filename": "1.pdf"}'
```

Expected response:
```json
{
  "url": "https://s3.amazonaws.com/...",
  "bucket": "your-bucket-name",
  "key": "uploads/1.pdf",
  "expires_in": 3600
}
```

### 3. Upload File to S3

```bash
# Extract the presigned URL from step 2
PRESIGNED_URL="https://s3.amazonaws.com/..."

curl -X PUT "$PRESIGNED_URL" --upload-file 1.pdf
```

### 4. Trigger Document Processing

```bash
curl -X POST https://<your-api-gateway-url>/process \
  -H "Content-Type: application/json" \
  -d '{
    "bucket": "your-bucket-name",
    "key": "uploads/1.pdf"
  }'
```

Expected response (immediate):
```json
{
  "status": "accepted",
  "message": "Document processing started in background",
  "bucket": "your-bucket-name",
  "key": "uploads/1.pdf"
}
```

### 5. Wait for Processing (30-60 seconds)

Monitor CloudWatch logs to see the detailed processing:

```bash
aws logs tail /aws/ecs/pharma-raganything-async --follow --region us-east-1
```

Look for these log markers:
- `📄 [BG_PROCESS] ===== DOCUMENT PROCESSING STARTED =====`
- `✅ [BG_PROCESS] Step 1 SUCCESS`
- `✅ [BG_PROCESS] Step 2 SUCCESS`
- `✅ [BG_PROCESS] Step 3 SUCCESS`
- `✅ [BG_PROCESS] Step 4 SUCCESS`
- `✅ [BG_PROCESS] Step 5 SUCCESS`
- `✅ [BG_PROCESS] ===== DOCUMENT PROCESSING COMPLETED =====`

### 6. Test RAG Query

```bash
curl -X POST https://<your-api-gateway-url>/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the main topic of the document?",
    "mode": "hybrid"
  }'
```

Expected response:
```json
{
  "query": "What is the main topic of the document?",
  "answer": "The main topic is...",
  "sources": [...],
  "confidence": 0.95,
  "mode": "hybrid",
  "status": "completed",
  "timing": {
    "query_duration": 2.34,
    "parse_duration": 0.01,
    "total_duration": 2.35
  }
}
```

## 📊 Step 5: Monitor Logs

Watch for detailed logs at each step:

### Document Processing Logs
```
📄 [BG_PROCESS] ===== DOCUMENT PROCESSING STARTED =====
📥 [BG_PROCESS] Step 1: Downloading from S3...
✅ [BG_PROCESS] Step 1 SUCCESS: Downloaded 2.45MB
🚀 [BG_PROCESS] Step 2: Getting RAG instance...
✅ [BG_PROCESS] Step 2 SUCCESS: RAG instance retrieved
🔍 [BG_PROCESS] Step 3: Parsing document...
✅ [BG_PROCESS] Step 3 SUCCESS: Document parsed
🔍 [BG_PROCESS] Step 4: Extracting chunks...
📦 [BG_PROCESS] Using native Docling chunks...
✅ [BG_PROCESS] Step 4 SUCCESS: Created 42 chunks
📥 [BG_PROCESS] Step 5: Inserting chunks...
✅ [BG_PROCESS] Step 5 SUCCESS: Chunks inserted successfully
✅ [BG_PROCESS] ===== DOCUMENT PROCESSING COMPLETED =====
✅ [BG_PROCESS] Total time: 15.234s
✅ [BG_PROCESS] Chunks inserted: 42
```

### Query Logs
```
🔍 [QUERY] ===== QUERY STARTED =====
🔍 [QUERY] Step 1: Parsing request...
🔍 [QUERY] Query: What is the main topic?
🔍 [QUERY] Mode: hybrid
✅ [QUERY] Step 1 SUCCESS
🔍 [QUERY] Step 2: Getting RAG instance...
✅ [QUERY] Step 2 SUCCESS
🔍 [QUERY] Step 3: Executing query...
✅ [QUERY] Step 3 SUCCESS
🔍 [QUERY] Query execution time: 2.456s
📝 [QUERY] Step 4: Parsing result...
✅ [QUERY] Step 4 SUCCESS
✅ [QUERY] ===== QUERY COMPLETED =====
✅ [QUERY] Total time: 2.567s
✅ [QUERY] Answer length: 245 chars
```

## 🔍 Troubleshooting

### If ECS Task Fails to Start

Check CloudWatch logs for container errors:
```bash
aws logs tail /aws/ecs/pharma-raganything-async --follow
```

### If Document Processing Fails

Look for error markers in logs:
```
❌ [BG_PROCESS] Step 3 FAILED: Parse error
❌ [BG_PROCESS] Traceback: ...
```

### If Query Returns No Results

1. Verify document was processed successfully
2. Check EFS data exists:
```bash
aws ecs execute-command --cluster ... --task ... --command "ls -la /rag-output/"
```

3. Check for query errors in logs:
```
❌ [QUERY] Step 3 FAILED: Query processing failed
```

## 📝 Summary of Latest Changes

This deployment includes:
- ✅ Async document processing (no timeouts)
- ✅ Comprehensive logging (5 steps for processing, 4 steps for queries)
- ✅ Native Docling chunking (fast, default)
- ✅ USE_LLM_CHUNKING option (configurable)
- ✅ Correct RAG-Anything API usage (parse_document + insert_content_list)
- ✅ Full error tracking and stack traces

## 🎯 Next Steps

1. Run the deployment commands above
2. Clear EFS data (optional)
3. Upload a test document
4. Wait for processing (check logs)
5. Query the RAG system
6. Verify results

