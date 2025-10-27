#!/bin/bash

set -e

echo "🧪 Testing Deployed RAG System"
echo "================================"
echo ""

# Configuration
API_URL="https://h51u75mco5.execute-api.us-east-1.amazonaws.com/dev"
ALB_URL="http://pharma-rag-alb-dev-2054947644.us-east-1.elb.amazonaws.com"

echo "1️⃣ Testing Health Endpoint..."
echo "================================"
curl -X GET $ALB_URL/health -s | jq '.'
echo ""

echo "2️⃣ Testing Get Chunks Endpoint..."
echo "================================"
curl -X GET "$ALB_URL/get_chunks?doc_id=1.pdf&limit=5" -s | jq '.'
echo ""

echo "3️⃣ Testing Analyze EFS Endpoint..."
echo "================================"
curl -X GET $ALB_URL/analyze_efs -s | jq '.'
echo ""

echo "✅ Test completed!"
echo ""
echo "Note: To upload documents, use the API Gateway: $API_URL"
echo "      The ALB is for RAG client endpoints only"
