# ============================================
# Single Dockerfile - RAG-Anything + Docling
# Python 3.12 slim with all dependencies
# Based on https://github.com/HKUDS/RAG-Anything
# ============================================
FROM --platform=linux/amd64 python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" \
    HF_HOME=/opt/models/ \
    TORCH_HOME=/opt/models/ \
    OMP_NUM_THREADS=4 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
        git \
        curl \
        wget \
        procps \
        tesseract-ocr \
        tesseract-ocr-eng \
        libtesseract-dev \
        libleptonica-dev \
        pkg-config \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
        libgcc-s1 \
        libx11-6 \
        libgl1-mesa-dri \
        ca-certificates \
        gnupg \
        lsb-release \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Install RAG-Anything with all extensions (includes most dependencies)
RUN pip install --no-cache-dir 'raganything[all]' boto3 flask

# Install Docling with CPU-only PyTorch and pytesseract
RUN pip install --no-cache-dir docling pytesseract --extra-index-url https://download.pytorch.org/whl/cpu

# Create models directory and download docling models
RUN mkdir -p /opt/models/ && \
    docling-tools models download

# Verify both RAG-Anything and Docling are available
RUN python3 -c "import raganything; print('RAG-Anything installed successfully')" && \
    python3 -c "import docling; print('Docling installed successfully')" && \
    python3 -c "import pytesseract; print('pytesseract installed successfully')" && \
    python3 -c "import flask; print('Flask installed successfully')" && \
    python3 -c "import boto3; print('Boto3 installed successfully')" && \
    echo "📦 [DOCKER] Models downloaded to:" && \
    ls -la /opt/models/ && \
    echo "📦 [DOCKER] Model files count: $(find /opt/models/ -type f | wc -l)"

# Copy RAG server script
COPY apps/rag_client.py /var/task/

# Set the CMD to run the RAG server
CMD ["python3", "/var/task/rag_client.py"]
