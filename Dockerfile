# ============================================
# RAG-Anything + Docling Dockerfile - Python 3.12 slim
# Based on https://github.com/HKUDS/RAG-Anything
# Bundles both RAG-Anything and Docling in single container
# ============================================
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
        git \
        curl \
        wget \
        libgl1-mesa-dri \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
        libgcc-s1 \
        libx11-6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Install RAG-Anything with all extensions
RUN pip install --no-cache-dir 'raganything[all]' boto3 requests flask

# Install Docling separately (not included in raganything[all])
RUN pip install --no-cache-dir docling

# Verify both RAG-Anything and Docling are available
RUN python3 -c "import raganything; print('RAG-Anything installed successfully')" && \
    python3 -c "import docling; print('Docling installed successfully')"

# Copy RAG server script
COPY apps/rag_client.py /var/task/

# Set the CMD to run the RAG server
CMD ["python3", "/var/task/rag_client.py"]
