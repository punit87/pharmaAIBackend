FROM python:3.9-slim

WORKDIR /opt/ml/code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY inference.py .

# Remove EXPOSE as serverless doesn't use a specific port
# EXPOSE 8080  # Not needed for serverless

ENV PYTHONUNBUFFERED=1

# Set a non-root user (good practice)
USER 1000

# No CMD needed for serverless - SageMaker handles execution
# CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "inference:app"]