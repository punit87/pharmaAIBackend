# RAG Client Flowchart - rag_client.py

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG-Anything Server                         │
│                    (Flask Application)                         │
└─────────────────────────────────────────────────────────────────┘
```

## 🔄 Main Flow Components

### 1. **Initialization & Configuration**
```
START
  │
  ├─ 📦 Import Dependencies
  │   ├─ Flask, asyncio, threading
  │   ├─ RAG-Anything, LightRAG
  │   └─ OpenAI, Boto3
  │
  ├─ ⚙️ Setup Logging
  │   ├─ Console Handler
  │   └─ File Handler (/tmp/rag_client.log)
  │
  ├─ 🌐 Global State Management
  │   ├─ _event_loop (None)
  │   ├─ _rag_instance (None)
  │   └─ _rag_lock (threading.Lock)
  │
  └─ 🚀 Start Flask Server
```

### 2. **Event Loop Management**
```
get_event_loop()
  │
  ├─ 🔍 Check if _event_loop exists
  │   ├─ YES → Return existing loop
  │   └─ NO → Create new event loop
  │       ├─ Create in separate thread
  │       ├─ Set as daemon thread
  │       └─ Start thread
  │
  └─ 🔄 Return persistent event loop
```

### 3. **Configuration Functions**
```
get_api_config()
  │
  ├─ 🔑 Get OpenAI API Key
  ├─ 🌐 Get Base URL (default: https://api.openai.com/v1)
  └─ 📋 Return config dict

get_rag_config()
  │
  ├─ 📁 Set working directory (/rag-output/)
  ├─ 🔍 Set parser (docling)
  ├─ 🔤 Set parse method (ocr)
  ├─ 🖼️ Enable image processing
  ├─ 📊 Enable table processing
  ├─ 🧮 Enable equation processing
  ├─ 🔍 Set OCR options (Tesseract)
  └─ 📋 Return RAGAnythingConfig

get_llm_model_func()
  │
  ├─ 🔧 Get API config
  ├─ 🤖 Create OpenAI completion function
  ├─ ⏱️ Add timing logs
  └─ 🔄 Return LLM function

get_vision_model_func()
  │
  ├─ 🖼️ Create VLM function
  ├─ 🔍 Handle image processing
  └─ 🔄 Return VLM function

get_embedding_func()
  │
  ├─ 🔗 Create embedding function
  ├─ 📏 Set dimension (1536)
  └─ 🔄 Return embedding function
```

### 4. **RAG Instance Management**
```
get_rag_instance()
  │
  ├─ 🔒 Acquire lock
  ├─ 🔍 Check if _rag_instance exists
  │   ├─ YES → Return existing instance
  │   └─ NO → Create new instance
  │       ├─ Get RAG config
  │       ├─ Get LLM function
  │       ├─ Get VLM function
  │       ├─ Get embedding function
  │       ├─ Create RAGAnything instance
  │       └─ Store in _rag_instance
  │
  └─ 🔓 Release lock
```

## 🌐 API Endpoints

### 1. **Health Check**
```
GET /health
  │
  ├─ 📊 Get system status
  ├─ 🔍 Check RAG initialization
  ├─ 📈 Get activity metrics
  └─ 📋 Return JSON response
```

### 2. **Document Processing**
```
POST /process
  │
  ├─ 📥 Parse request data
  │   ├─ source (S3 URL)
  │   └─ output_dir
  │
  ├─ 🔄 Run async processing
  │   ├─ Download from S3
  │   ├─ Get RAG instance
  │   ├─ Process document
  │   └─ Clean up temp files
  │
  ├─ ⏱️ Log timing information
  └─ 📋 Return processing result
```

### 3. **Standard Query**
```
POST /query
  │
  ├─ 📥 Parse request data
  │   ├─ query (text)
  │   ├─ mode (naive/hybrid)
  │   └─ vlm (auto/true/false)
  │
  ├─ 🔄 Run async query
  │   ├─ Get RAG instance
  │   ├─ Process query
  │   └─ Get response
  │
  ├─ ⏱️ Log timing information
  └─ 📋 Return query result
```

### 4. **Multimodal Query**
```
POST /query_multimodal
  │
  ├─ 📥 Parse request data
  │   ├─ query (text)
  │   ├─ mode (naive/hybrid)
  │   └─ vlm (auto/true/false)
  │
  ├─ 🔄 Run async multimodal query
  │   ├─ Get RAG instance
  │   ├─ Process with VLM
  │   └─ Get response
  │
  ├─ ⏱️ Log timing information
  └─ 📋 Return multimodal result
```

### 5. **EFS Analysis**
```
GET /analyze_efs
  │
  ├─ 📁 Walk EFS directory
  ├─ 📊 Collect file statistics
  │   ├─ Total files
  │   ├─ File sizes
  │   ├─ Chunk files
  │   ├─ Embedding files
  │   └─ Metadata files
  │
  ├─ 📖 Read sample files
  │   ├─ Chunk content
  │   └─ Metadata content
  │
  └─ 📋 Return analysis JSON
```

### 6. **Get Chunks**
```
GET /get_chunks
  │
  ├─ 📁 Read chunk files
  │   ├─ kv_store_text_chunks.json
  │   ├─ kv_store_entity_chunks.json
  │   ├─ kv_store_relation_chunks.json
  │   └─ vdb_chunks.json
  │
  ├─ 📊 Collect chunk data
  └─ 📋 Return chunks JSON
```

## 🔄 Async Processing Flow

```
run_async(coro)
  │
  ├─ 🔄 Get event loop
  ├─ 🚀 Submit coroutine
  ├─ ⏳ Wait for result
  └─ 📋 Return result
```

## 🧹 Cleanup & Shutdown

```
cleanup_event_loop()
  │
  ├─ 🔍 Check if loop exists
  ├─ 🛑 Stop event loop
  ├─ 🔒 Close loop
  └─ 🧹 Clean up resources
```

## 📊 Key Features

### **Performance Optimizations**
- ✅ Persistent event loop (no cold start)
- ✅ Lazy RAG initialization
- ✅ Thread-safe singleton pattern
- ✅ Memory-efficient caching
- ✅ Comprehensive logging

### **OCR Capabilities**
- ✅ Tesseract OCR engine
- ✅ Full-page OCR processing
- ✅ English language support
- ✅ Image, table, equation processing

### **Monitoring & Debugging**
- ✅ Detailed timing logs
- ✅ EFS content analysis
- ✅ Chunk inspection
- ✅ Health check endpoint

## 🎯 Main Workflow

```
1. Server Start
   ├─ Initialize logging
   ├─ Setup global state
   └─ Start Flask app

2. First Request
   ├─ Create event loop
   ├─ Initialize RAG instance
   └─ Process request

3. Subsequent Requests
   ├─ Use existing event loop
   ├─ Use existing RAG instance
   └─ Process requests efficiently

4. Document Processing
   ├─ Download from S3
   ├─ Parse with Docling + OCR
   ├─ Create chunks
   ├─ Generate embeddings
   └─ Store in EFS

5. Query Processing
   ├─ Get RAG instance
   ├─ Process query
   ├─ Retrieve relevant chunks
   ├─ Generate response
   └─ Return result
```

## 🔧 Configuration

### **Environment Variables**
- `OUTPUT_DIR`: Working directory (/rag-output/)
- `PARSER`: Parser type (docling)
- `PARSE_METHOD`: Parse method (ocr)
- `OPENAI_API_KEY`: OpenAI API key
- `NEO4J_URI`: Neo4j connection string
- `NEO4J_USERNAME`: Neo4j username
- `NEO4J_PASSWORD`: Neo4j password

### **OCR Settings**
- Engine: Tesseract
- Language: English (eng)
- Force full page OCR: True
- Image processing: Enabled
- Table processing: Enabled
- Equation processing: Enabled
