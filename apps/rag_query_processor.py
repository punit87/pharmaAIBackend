#!/usr/bin/env python3
"""
RAG-Anything Query Processing Service
Handles RAG queries and generates responses using OpenAI
"""

import os
import sys
import json
import boto3
from neo4j import GraphDatabase
import openai
from datetime import datetime
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class RagQueryProcessor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.s3_bucket = os.environ['S3_BUCKET']
        self.query = os.environ.get('QUERY', '')
        
        # Neo4j connection
        self.neo4j_uri = os.environ['NEO4J_URI']
        self.neo4j_username = os.environ['NEO4J_USERNAME']
        self.neo4j_password = os.environ['NEO4J_PASSWORD']
        self.driver = GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_username, self.neo4j_password)
        )
        
        # OpenAI setup
        openai.api_key = os.environ['OPENAI_API_KEY']
        
    def process_query(self):
        """Main query processing function"""
        try:
            print(f"Processing query: {self.query}")
            
            # Generate query embedding
            query_embedding = self._generate_query_embedding(self.query)
            
            # Find relevant chunks using vector similarity
            relevant_chunks = self._find_relevant_chunks(query_embedding)
            
            # Retrieve context from Neo4j
            context = self._retrieve_context(relevant_chunks)
            
            # Generate response using OpenAI
            response = self._generate_response(self.query, context)
            
            # Store query and response
            self._store_query_response(self.query, response, relevant_chunks)
            
            print("Query processing completed successfully")
            print(f"Response: {response}")
            
        except Exception as e:
            print(f"Error processing query: {str(e)}")
            sys.exit(1)
        finally:
            self.driver.close()
    
    def _generate_query_embedding(self, query):
        """Generate embedding for the query using OpenAI"""
        try:
            response = openai.Embedding.create(
                input=query,
                model="text-embedding-ada-002"
            )
            return response['data'][0]['embedding']
        except Exception as e:
            print(f"Failed to generate query embedding: {e}")
            return []
    
    def _find_relevant_chunks(self, query_embedding, top_k=5):
        """Find most relevant chunks using vector similarity"""
        if not query_embedding:
            return []
        
        relevant_chunks = []
        
        with self.driver.session() as session:
            # Get all chunks with embeddings
            result = session.run("""
                MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
                WHERE c.embedding IS NOT NULL
                RETURN c.text as text, c.embedding as embedding, c.chunk_index as index,
                       d.key as document_key
            """)
            
            similarities = []
            for record in result:
                chunk_text = record['text']
                chunk_embedding = record['embedding']
                chunk_index = record['index']
                document_key = record['document_key']
                
                if chunk_embedding:
                    # Calculate cosine similarity
                    similarity = cosine_similarity(
                        [query_embedding], 
                        [chunk_embedding]
                    )[0][0]
                    
                    similarities.append({
                        'text': chunk_text,
                        'similarity': similarity,
                        'index': chunk_index,
                        'document_key': document_key
                    })
            
            # Sort by similarity and return top_k
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            relevant_chunks = similarities[:top_k]
        
        return relevant_chunks
    
    def _retrieve_context(self, relevant_chunks):
        """Retrieve additional context from Neo4j graph"""
        context = {
            'chunks': relevant_chunks,
            'related_documents': [],
            'related_tables': [],
            'related_images': []
        }
        
        if not relevant_chunks:
            return context
        
        with self.driver.session() as session:
            # Get related documents
            document_keys = list(set([chunk['document_key'] for chunk in relevant_chunks]))
            
            for doc_key in document_keys:
                # Get tables from same documents
                table_result = session.run("""
                    MATCH (d:Document {key: $key})-[:CONTAINS]->(t:Table)
                    RETURN t.caption as caption, t.content as content
                """, key=doc_key)
                
                for record in table_result:
                    context['related_tables'].append({
                        'caption': record['caption'],
                        'content': record['content']
                    })
                
                # Get images from same documents
                image_result = session.run("""
                    MATCH (d:Document {key: $key})-[:CONTAINS]->(i:Image)
                    RETURN i.caption as caption, i.ocr_text as ocr_text
                """, key=doc_key)
                
                for record in image_result:
                    context['related_images'].append({
                        'caption': record['caption'],
                        'ocr_text': record['ocr_text']
                    })
        
        return context
    
    def _generate_response(self, query, context):
        """Generate response using OpenAI GPT"""
        # Prepare context text
        context_text = ""
        
        # Add relevant chunks
        for chunk in context['chunks']:
            context_text += f"Document excerpt: {chunk['text']}\n\n"
        
        # Add related tables
        for table in context['related_tables']:
            context_text += f"Table ({table['caption']}): {table['content']}\n\n"
        
        # Add related images OCR text
        for image in context['related_images']:
            if image['ocr_text']:
                context_text += f"Image text ({image['caption']}): {image['ocr_text']}\n\n"
        
        # Generate response
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that answers questions based on the provided document context. Use only the information from the context to answer questions. If the context doesn't contain enough information to answer the question, say so."
                    },
                    {
                        "role": "user",
                        "content": f"Context:\n{context_text}\n\nQuestion: {query}"
                    }
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Failed to generate response: {e}")
            return "I apologize, but I couldn't generate a response at this time."
    
    def _store_query_response(self, query, response, relevant_chunks):
        """Store query and response in Neo4j and S3"""
        # Store in Neo4j
        with self.driver.session() as session:
            session.run("""
                CREATE (q:Query {
                    text: $query,
                    response: $response,
                    timestamp: datetime()
                })
            """, query=query, response=response)
            
            # Link to relevant chunks
            for chunk in relevant_chunks:
                session.run("""
                    MATCH (q:Query {text: $query})
                    MATCH (c:Chunk {chunk_index: $index, document_key: $doc_key})
                    CREATE (q)-[:REFERENCES]->(c)
                """, query=query, index=chunk['index'], doc_key=chunk['document_key'])
        
        # Store in S3
        query_data = {
            'query': query,
            'response': response,
            'relevant_chunks': relevant_chunks,
            'timestamp': datetime.now().isoformat()
        }
        
        query_key = f"queries/{datetime.now().strftime('%Y/%m/%d')}/{os.environ.get('AWS_REQUEST_ID', 'unknown')}.json"
        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=query_key,
            Body=json.dumps(query_data, indent=2),
            ContentType='application/json'
        )
        
        print(f"Stored query data at: s3://{self.s3_bucket}/{query_key}")

if __name__ == "__main__":
    processor = RagQueryProcessor()
    processor.process_query()
