# Multi-stage build for optimized image size
FROM jitesoft/tesseract-ocr:5-24.04 AS builder

USER root

# Install Python and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-pip \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install uv for fastest installation
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir uv

# Install dependencies with uv (much faster than pip)
RUN uv pip install --no-cache \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --no-cache docling "raganything[all]"

# Install FastAPI and dependencies
RUN uv pip install --no-cache fastapi uvicorn[standard] python-multipart boto3 requests

# ============================================
# Runtime stage - smaller final image
# ============================================
FROM jitesoft/tesseract-ocr:5-24.04

USER root

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3-pip \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create app user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app /tmp/raganything && \
    chown -R appuser:appuser /app /tmp/raganything

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    RAG_PARSER=docling \
    TEMP=/tmp/raganything \
    TMPDIR=/tmp/raganything \
    PORT=8080

WORKDIR /app

# Copy application files
COPY app/ /app/

# Switch to non-root user
USER appuser

# Expose port for Fargate
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Start application
CMD ["python3", "main.py"]