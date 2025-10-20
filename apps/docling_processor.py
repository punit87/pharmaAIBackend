#!/usr/bin/env python3
"""
Docling Document Processing Service
Processes uploaded documents and extracts content for RAG indexing
"""

import os
import sys
import json
import boto3
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
import pytesseract
from neo4j import GraphDatabase
import openai
from datetime import datetime

class DoclingProcessor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.s3_bucket = os.environ['S3_BUCKET']
        self.s3_key = os.environ.get('S3_KEY', '')
        
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
        
        # Initialize Docling converter
        self.converter = DocumentConverter()
        
    def process_document(self):
        """Main processing function"""
        try:
            print(f"Processing document: s3://{self.s3_bucket}/{self.s3_key}")
            
            # Download document from S3
            local_file_path = f"/tmp/{os.path.basename(self.s3_key)}"
            self.s3_client.download_file(self.s3_bucket, self.s3_key, local_file_path)
            
            # Convert document using Docling
            result = self.converter.convert(local_file_path)
            
            # Extract text content
            text_content = result.document.export_to_markdown()
            
            # Extract tables
            tables = []
            for table in result.document.tables:
                tables.append({
                    'caption': table.caption,
                    'content': table.export_to_markdown()
                })
            
            # Extract images and perform OCR
            images_with_ocr = []
            for image in result.document.images:
                try:
                    # Perform OCR on image
                    ocr_text = pytesseract.image_to_string(image.image)
                    images_with_ocr.append({
                        'caption': image.caption,
                        'ocr_text': ocr_text
                    })
                except Exception as e:
                    print(f"OCR failed for image: {e}")
                    images_with_ocr.append({
                        'caption': image.caption,
                        'ocr_text': ''
                    })
            
            # Generate embeddings for chunks
            chunks = self._chunk_text(text_content)
            embeddings = self._generate_embeddings(chunks)
            
            # Store in Neo4j
            self._store_in_neo4j(self.s3_key, text_content, tables, images_with_ocr, chunks, embeddings)
            
            # Store processed data in S3
            self._store_processed_data(text_content, tables, images_with_ocr, chunks, embeddings)
            
            print("Document processing completed successfully")
            
        except Exception as e:
            print(f"Error processing document: {str(e)}")
            sys.exit(1)
        finally:
            self.driver.close()
    
    def _chunk_text(self, text, chunk_size=1000, overlap=200):
        """Split text into overlapping chunks"""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append({
                'text': chunk,
                'start': start,
                'end': end
            })
            start = end - overlap
        return chunks
    
    def _generate_embeddings(self, chunks):
        """Generate embeddings for text chunks using OpenAI"""
        embeddings = []
        for chunk in chunks:
            try:
                response = openai.Embedding.create(
                    input=chunk['text'],
                    model="text-embedding-ada-002"
                )
                embeddings.append({
                    'text': chunk['text'],
                    'embedding': response['data'][0]['embedding'],
                    'start': chunk['start'],
                    'end': chunk['end']
                })
            except Exception as e:
                print(f"Failed to generate embedding: {e}")
                embeddings.append({
                    'text': chunk['text'],
                    'embedding': [],
                    'start': chunk['start'],
                    'end': chunk['end']
                })
        return embeddings
    
    def _store_in_neo4j(self, document_key, text_content, tables, images, chunks, embeddings):
        """Store document data in Neo4j graph database"""
        with self.driver.session() as session:
            # Create document node
            session.run("""
                CREATE (d:Document {
                    key: $key,
                    processed_at: datetime(),
                    text_length: $text_length,
                    chunk_count: $chunk_count
                })
            """, key=document_key, text_length=len(text_content), chunk_count=len(chunks))
            
            # Create chunk nodes
            for i, chunk in enumerate(chunks):
                session.run("""
                    MATCH (d:Document {key: $key})
                    CREATE (c:Chunk {
                        text: $text,
                        start_pos: $start,
                        end_pos: $end,
                        chunk_index: $index
                    })
                    CREATE (d)-[:CONTAINS]->(c)
                """, key=document_key, text=chunk['text'], start=chunk['start'], 
                     end=chunk['end'], index=i)
            
            # Create table nodes
            for i, table in enumerate(tables):
                session.run("""
                    MATCH (d:Document {key: $key})
                    CREATE (t:Table {
                        caption: $caption,
                        content: $content,
                        table_index: $index
                    })
                    CREATE (d)-[:CONTAINS]->(t)
                """, key=document_key, caption=table['caption'], 
                     content=table['content'], index=i)
            
            # Create image nodes
            for i, image in enumerate(images):
                session.run("""
                    MATCH (d:Document {key: $key})
                    CREATE (i:Image {
                        caption: $caption,
                        ocr_text: $ocr_text,
                        image_index: $index
                    })
                    CREATE (d)-[:CONTAINS]->(i)
                """, key=document_key, caption=image['caption'], 
                     ocr_text=image['ocr_text'], index=i)
    
    def _store_processed_data(self, text_content, tables, images, chunks, embeddings):
        """Store processed data in S3"""
        processed_data = {
            'document_key': self.s3_key,
            'processed_at': datetime.now().isoformat(),
            'text_content': text_content,
            'tables': tables,
            'images': images,
            'chunks': chunks,
            'embeddings': embeddings
        }
        
        # Store as JSON in S3
        processed_key = f"processed/{self.s3_key.replace('uploads/', '')}.json"
        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=processed_key,
            Body=json.dumps(processed_data, indent=2),
            ContentType='application/json'
        )
        
        print(f"Stored processed data at: s3://{self.s3_bucket}/{processed_key}")

if __name__ == "__main__":
    processor = DoclingProcessor()
    processor.process_document()
