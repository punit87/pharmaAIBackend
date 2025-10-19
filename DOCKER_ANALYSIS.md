# Docker Image Analysis & Requirements

## 📊 **Estimated Image Sizes**

Based on the dependencies and configurations:

### **RAG-Anything Image (All Features + LibreOffice)**
- **Base**: `libreofficedocker/libreoffice-unoserver:latest` (~400MB)
- **Python 3.11**: Additional Python installation (~100MB)
- **Python Dependencies**: `raganything` + all optional packages (~400MB)
- **Additional Libraries**: Pillow + ReportLab + system packages (~200MB)
- **Total Estimated Size**: **~1.1GB**

### **Key Optimizations**
- ✅ **Multi-stage build** reduces final image size
- ✅ **Official LibreOffice image** as base (more reliable)
- ✅ **Headless LibreOffice** (optimized for serverless)
- ✅ **All features included** by default

## 🏗️ **Complete Requirements Analysis**

### **RAG-Anything End-to-End Requirements**

#### **System Dependencies (MANDATORY)**
```bash
# Ubuntu/Debian
sudo apt-get install libreoffice git curl wget build-essential

# macOS
brew install --cask libreoffice

# Windows
# Download from https://www.libreoffice.org/download/download/
```

#### **Python Dependencies**

**Basic Configuration:**
```bash
pip install raganything
```

**All Features Configuration:**
```bash
pip install 'raganything[all]'
```

**Individual Optional Dependencies:**
- `[image]` - BMP, TIFF, GIF, WebP support (requires Pillow)
- `[text]` - TXT, MD support (requires ReportLab)
- `[all]` - All optional features

#### **Office Document Processing Requirements**
- **LibreOffice** (MANDATORY for .doc, .docx, .ppt, .pptx, .xls, .xlsx)
- **Pillow** (for extended image formats)
- **ReportLab** (for text file processing)

### **Docling Requirements**

#### **System Dependencies**
```bash
# Ubuntu/Debian
sudo apt-get install git curl wget build-essential

# Python
pip install docling
```

## 🚀 **GitHub Actions Workflow Features**

### **Workflow Inputs**
- ✅ **Build Docling**: Boolean checkbox
- ✅ **Build RAG-Anything**: Boolean checkbox
- ✅ **RAG-Anything Config**: Dropdown (basic/all)
- ✅ **RAG-Anything Parser**: Dropdown (mineru/docling)
- ✅ **Custom Tag**: Text input

### **Conditional Builds**
- Jobs only run if selected
- Different configurations based on inputs
- Optimized builds for different use cases

## 📋 **Lambda Function Requirements**

### **Memory Requirements**
- **Docling Lambda**: 512MB - 1GB
- **RAG-Anything Lambda**: 2GB - 3GB (due to LibreOffice)

### **Timeout Requirements**
- **Docling Lambda**: 5-10 minutes
- **RAG-Anything Lambda**: 10-15 minutes

### **Environment Variables**
```bash
# Required for RAG-Anything
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=your_base_url  # Optional

# S3 Buckets
DOCLING_INPUT_BUCKET=docling-input
DOCLING_OUTPUT_BUCKET=docling-output
RAG_EMBEDDINGS_BUCKET=rag-embeddings
RAG_STORAGE_BUCKET=rag-storage
```

## 🔧 **Dockerfile Optimizations**

### **Multi-stage Builds**
- Separate stages for dependencies and runtime
- Smaller final images
- Better caching

### **Layer Optimization**
- Combine RUN commands
- Use .dockerignore
- Minimize layers

### **Security**
- Non-root user
- Minimal attack surface
- Regular base image updates

## 💰 **Cost Implications**

### **Image Storage**
- **Docling**: ~350MB × $0.10/GB/month = $0.035/month
- **RAG-Anything Basic**: ~1.25GB × $0.10/GB/month = $0.125/month
- **RAG-Anything All**: ~1.45GB × $0.10/GB/month = $0.145/month

### **Lambda Execution**
- **Docling**: ~$0.0000166667 per GB-second
- **RAG-Anything**: ~$0.0000166667 per GB-second (higher memory)

### **Total Monthly Cost (Estimated)**
- **Image Storage**: ~$0.30/month
- **Lambda Execution**: ~$5-20/month (depending on usage)
- **S3 Storage**: ~$1-5/month
- **API Gateway**: ~$1-3/month

**Total**: ~$7-28/month for moderate usage

## 🎯 **Recommended Configurations**

### **Development/Testing**
- **Docling**: Basic build
- **RAG-Anything**: Basic configuration
- **Memory**: 1GB for Docling, 2GB for RAG-Anything

### **Production**
- **Docling**: Basic build
- **RAG-Anything**: All features configuration
- **Memory**: 1GB for Docling, 3GB for RAG-Anything

### **High-Volume Processing**
- **Docling**: Basic build
- **RAG-Anything**: All features configuration
- **Memory**: 2GB for Docling, 3GB for RAG-Anything
- **Consider**: ECS Fargate for better performance
