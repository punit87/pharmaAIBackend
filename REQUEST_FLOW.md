# Request Flow - Document Upload & RAG Query

## 📄 DOCUMENT UPLOAD FLOW

```
┌─────────────┐
│   CLIENT    │
└──────┬──────┘
       │ 1. Request presigned URL
       ▼
┌─────────────────────────────────────┐
│  API Gateway                         │
│  /presigned-url                      │
└──────┬───────────────────────────────┘
       │
       │ 2. Forward to Lambda
       ▼
┌─────────────────────────────────────┐
│  Lambda Function                    │
│  (presigned_url.py)                 │
│  - Generate S3 presigned URL        │
└──────┬───────────────────────────────┘
       │
       │ 3. Return presigned URL
       ▼
┌─────────────┐
│   CLIENT    │
└──────┬──────┘
       │ 4. Upload file directly to S3
       ▼
┌─────────────────────────────────────┐
│  AWS S3 Bucket                      │
│  - Store uploaded document           │
└──────┬───────────────────────────────┘
       │
       │ 5. Trigger event
       ▼
┌─────────────────────────────────────┐
│  Lambda Function                    │
│  (document_processor.py)            │
│  - Receives S3 event                │
│  - Extracts bucket & key            │
└──────┬───────────────────────────────┘
       │
       │ 6. Call ECS /process endpoint
       ▼
┌─────────────────────────────────────┐
│  Application Load Balancer (ALB)     │
│  - Routes traffic to ECS tasks        │
└──────┬───────────────────────────────┘
       │
       │ 7. Forward to ECS task
       ▼
┌─────────────────────────────────────┐
│  ECS Fargate Task (RAG Client)      │
│  POST /process                       │
│                                      │
│  ├─ Parse request data              │
│  ├─ Extract s3_bucket, s3_key       │
│  ├─ Submit to ThreadPoolExecutor     │
│  └─ Return immediately:              │
│     {                                │
│       "status": "accepted",          │
│       "message": "processing...",    │
│       "bucket": "...",               │
│       "key": "..."                    │
│     }                                │
└──────┬───────────────────────────────┘
       │
       │ 8. HTTP 200 Response
       ▼
┌─────────────┐
│   CLIENT    │ ← Receives immediate response
└─────────────┘


┌─────────────────────────────────────────┐
│  BACKGROUND THREAD (ThreadPoolExecutor)  │
│  process_document_background()          │
│                                          │
│  Step 1: Download from S3               │
│  ├─ Connect to S3 client               │
│  ├─ Download file to /tmp/             │
│  └─ Log file size                      │
│                                          │
│  Step 2: Get RAG Instance               │
│  ├─ Call get_rag_instance()            │
│  └─ Return RAGAnything instance         │
│                                          │
│  Step 3: Parse Document                  │
│  ├─ Call rag.parse_document()           │
│  ├─ Parse with Docling (OCR)            │
│  └─ Return structured elements          │
│                                          │
│  Step 4: Extract Chunks                 │
│  ├─ Check USE_LLM_CHUNKING flag        │
│  │                                      │
│  ├─ IF LLM_CHUNKING=true:              │
│  │  ├─ Convert to markdown              │
│  │  ├─ Call custom_llm_chunking()       │
│  │  └─ GPT-4o-mini chunks content       │
│  │                                      │
│  └─ ELSE (default):                    │
│     ├─ Extract native Docling chunks   │
│     └─ Fast text-based extraction       │
│                                          │
│  Step 5: Insert into LightRAG           │
│  ├─ Call rag.insert_content_list()     │
│  ├─ Insert chunks into vector store    │
│  ├─ Generate embeddings                │
│  └─ Store on EFS                       │
│                                          │
│  Cleanup:                               │
│  └─ Delete temp file                   │
└─────────────────────────────────────────┘
```

---

## 🔍 RAG QUERY FLOW

```
┌─────────────┐
│   CLIENT    │
└──────┬──────┘
       │ 1. POST /query
       │    {
       │      "query": "What is...?",
       │      "mode": "hybrid"
       │    }
       ▼
┌─────────────────────────────────────┐
│  API Gateway                         │
│  POST /rag-query                     │
│  - 30s timeout                      │
└──────┬───────────────────────────────┘
       │
       │ 2. Forward to Lambda
       ▼
┌─────────────────────────────────────┐
│  Lambda Function                    │
│  (rag_query.py)                     │
│  - Parse request                     │
│  - Extract query & mode              │
└──────┬───────────────────────────────┘
       │
       │ 3. Call ECS /query
       ▼
┌─────────────────────────────────────┐
│  Application Load Balancer (ALB)     │
│  - Routes to ECS tasks                │
└──────┬───────────────────────────────┘
       │
       │ 4. Forward to ECS task
       ▼
┌─────────────────────────────────────┐
│  ECS Fargate Task (RAG Client)      │
│  POST /query                         │
│                                      │
│  Step 1: Parse Request              │
│  ├─ Extract query & mode            │
│  └─ Validate input                  │
│                                      │
│  Step 2: Get RAG Instance            │
│  ├─ Call get_rag_instance()         │
│  └─ Return cached or new instance   │
│                                      │
│  Step 3: Execute Query               │
│  ├─ Call rag.aquery(query, mode)    │
│  │                                   │
│  ├─ IF mode="hybrid":               │
│  │  ├─ Hybrid RAG (embedding + KG)  │
│  │  └─ Returns answer + sources      │
│  │                                   │
│  ├─ IF mode="naive":                │
│  │  ├─ Naive RAG (embedding only)   │
│  │  └─ Returns answer + sources     │
│  │                                   │
│  └─ IF mode="local":                │
│     ├─ Local RAG (KG only)          │
│     └─ Returns answer + sources      │
│                                      │
│  Step 4: Parse Result                │
│  ├─ Extract answer                   │
│  ├─ Extract sources                  │
│  ├─ Extract confidence               │
│  └─ Format response                  │
│                                      │
│  Return:                             │
│  {                                   │
│    "query": "...",                   │
│    "answer": "...",                  │
│    "sources": [...],                 │
│    "confidence": 0.95,               │
│    "mode": "hybrid",                 │
│    "status": "completed",            │
│    "timing": {                       │
│      "query_duration": 2.34,        │
│      "parse_duration": 0.01,        │
│      "total_duration": 2.35         │
│    }                                  │
│  }                                   │
└──────┬───────────────────────────────┘
       │
       │ 5. HTTP 200 Response
       ▼
┌─────────────┐
│   CLIENT    │ ← Receives answer
└─────────────┘


┌─────────────────────────────────────────┐
│  UNDER THE HOOD (LightRAG)               │
│                                          │
│  When rag.aquery() is called:           │
│                                          │
│  1. Embedding Lookup                     │
│     ├─ Generate query embedding         │
│     ├─ Search vector store (EFS)        │
│     └─ Find top-k similar chunks        │
│                                          │
│  2. Knowledge Graph Lookup             │
│     ├─ Query KG for related entities    │
│     ├─ Traverse relationships           │
│     └─ Extract context                  │
│                                          │
│  3. Context Assembly                    │
│     ├─ Combine relevant chunks          │
│     ├─ Add KG context                   │
│     └─ Format for LLM                   │
│                                          │
│  4. LLM Generation                      │
│     ├─ Send prompt + context to GPT     │
│     ├─ Generate answer                  │
│     ├─ Extract sources                  │
│     └─ Return to client                 │
└─────────────────────────────────────────┘
```

---

## 🔄 COMPONENT INTERACTIONS

```
                    ┌─────────────┐
                    │   CLIENT    │
                    └─────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   ┌─────────┐      ┌─────────┐      ┌─────────┐
   │ Upload  │      │  Query  │      │Health   │
   │ Flow    │      │  Flow   │      │ Check   │
   └────┬────┘      └────┬────┘      └────┬────┘
        │                 │                 │
        ▼                 ▼                 ▼
┌─────────────┐    ┌─────────────┐   ┌─────────────┐
│   API       │    │   API       │   │   API       │
│  Gateway    │    │  Gateway    │   │  Gateway    │
└──────┬──────┘    └──────┬──────┘   └──────┬──────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────┐    ┌─────────────┐   ┌─────────────┐
│  Lambda     │    │  Lambda     │   │  Lambda     │
│ (presigned  │    │ (rag_query   │   │ (health     │
│   _url)     │    │   .py)      │   │   .py)      │
└──────┬──────┘    └──────┬──────┘   └──────┬──────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────┐    ┌─────────────┐   ┌─────────────┐
│     S3      │    │     ALB     │   │     ALB     │
│   Storage   │    │             │   │             │
└──────┬──────┘    └──────┬──────┘   └──────┬──────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────┐    ┌─────────────┐   ┌─────────────┐
│   Lambda    │    │   ECS       │   │   ECS       │
│(processor)  │    │  Fargate    │   │  Fargate    │
└──────┬──────┘    └──────┬──────┘   └──────┬──────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────┐    ┌─────────────┐   ┌─────────────┐
│     ALB     │    │    RAG      │   │     RAG     │
│             │    │  Client     │   │   Client    │
└──────┬──────┘    └──────┬──────┘   └──────┬──────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────┐    ┌─────────────┐   ┌─────────────┐
│   ECS       │    │  LightRAG   │   │  LightRAG   │
│  Fargate    │    │             │   │             │
└──────┬──────┘    └──────┬──────┘   └──────┬──────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────┐    ┌─────────────┐   ┌─────────────┐
│   RAG       │    │     EFS     │   │     EFS     │
│  Client     │    │  (Storage)  │   │  (Storage)  │
└─────────────┘    └─────────────┘   └─────────────┘
```

---

## 📊 STORAGE LAYERS

```
┌──────────────────────────────────────────┐
│  EFS (Elastic File System)               │
│  - Persistent storage across ECS tasks    │
│  - Shared across all task instances       │
│                                            │
│  Structure:                                │
│  /rag-output/                              │
│    ├── chunks/                             │
│    │   └── embeddings.json                 │
│    ├── kg/                                 │
│    │   ├── entities.json                   │
│    │   ├── relations.json                  │
│    │   └── metadata.json                   │
│    └── status/                             │
│        └── pipeline_status.json             │
│                                            │
│  Data Flow:                                │
│  1. Document processed → Chunks saved     │
│  2. Embeddings generated → Stored in EFS  │
│  3. Knowledge Graph built → Stored in EFS │
│  4. Query → Reads from EFS                │
└────────────────────────────────────────────┘
```

---

## 🎯 KEY ENDPOINTS

### Document Upload
- **GET /presigned-url** → Get S3 upload URL
- **POST /process** → Trigger document processing (returns immediately)
- **Background**: Download → Parse → Chunk → Insert

### RAG Query  
- **POST /query** → Query RAG system (returns answer + sources)
- **POST /health** → Check ECS task status

### Processing Steps
1. S3 Download ✅
2. RAG Instance ✅
3. Document Parsing ✅
4. Chunk Extraction ✅
5. Data Insertion ✅

