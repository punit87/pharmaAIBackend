import json
import os
import boto3
import logging
from typing import Dict, List, Any, Optional, Union
from io import BytesIO
import base64

# Docling imports
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# Tesseract imports
import pytesseract
from PIL import Image

# Additional processing imports
import re
from dataclasses import dataclass
from enum import Enum

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')

class ChunkingStrategy(Enum):
    """Available chunking strategies for document processing"""
    FIXED_SIZE = "fixed_size"
    SENTENCE_BASED = "sentence_based"
    PARAGRAPH_BASED = "paragraph_based"
    SECTION_BASED = "section_based"
    SEMANTIC_CHUNKING = "semantic_chunking"
    TABLE_AWARE = "table_aware"

@dataclass
class ChunkingConfig:
    """Configuration for document chunking"""
    strategy: ChunkingStrategy
    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_size: int = 100
    max_chunk_size: int = 2000
    respect_sentence_boundaries: bool = True
    respect_paragraph_boundaries: bool = True

@dataclass
class DocumentProcessingResult:
    """Result of document processing"""
    success: bool
    content: str
    chunks: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    error: Optional[str] = None

class DoclingLambdaHandler:
    """Main handler class for Docling document processing in AWS Lambda"""
    
    def __init__(self):
        """Initialize the handler with Docling converter and configuration"""
        try:
            # Initialize Docling converter with optimized settings
            self.converter = DocumentConverter()
            
            # Configure Tesseract
            self._configure_tesseract()
            
            # Default chunking configuration
            self.default_chunking = ChunkingConfig(
                strategy=ChunkingStrategy.SENTENCE_BASED,
                chunk_size=1000,
                chunk_overlap=200
            )
            
            logger.info("DoclingLambdaHandler initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize DoclingLambdaHandler: {str(e)}")
            raise
    
    def _configure_tesseract(self):
        """Configure Tesseract OCR settings"""
        try:
            # Set Tesseract path if needed
            if 'TESSDATA_PREFIX' in os.environ:
                pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
            
            # Test Tesseract
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract version: {version}")
            
        except Exception as e:
            logger.warning(f"Tesseract configuration warning: {str(e)}")
    
    def process_document(self, 
                        document_source: str, 
                        chunking_config: Optional[ChunkingConfig] = None,
                        output_format: str = "markdown") -> DocumentProcessingResult:
        """
        Process a document using Docling with specified chunking strategy
        
        Args:
            document_source: URL, file path, or base64 encoded content
            chunking_config: Configuration for document chunking
            output_format: Output format (markdown, html, json)
        
        Returns:
            DocumentProcessingResult with processed content and chunks
        """
        try:
            # Use default chunking if not provided
            if chunking_config is None:
                chunking_config = self.default_chunking
            
            # Process document with Docling
            logger.info(f"Processing document: {document_source[:100]}...")
            result = self.converter.convert(document_source)
            
            # Extract content based on output format
            if output_format.lower() == "markdown":
                content = result.document.export_to_markdown()
            elif output_format.lower() == "html":
                content = result.document.export_to_html()
            elif output_format.lower() == "json":
                content = result.document.export_to_dict()
            else:
                content = result.document.export_to_markdown()
            
            # Extract metadata
            metadata = self._extract_metadata(result.document)
            
            # Apply chunking strategy
            chunks = self._chunk_content(content, chunking_config, metadata)
            
            return DocumentProcessingResult(
                success=True,
                content=content,
                chunks=chunks,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}")
            return DocumentProcessingResult(
                success=False,
                content="",
                chunks=[],
                metadata={},
                error=str(e)
            )
    
    def _extract_metadata(self, document) -> Dict[str, Any]:
        """Extract metadata from the processed document"""
        metadata = {
            "title": getattr(document, "title", "Unknown"),
            "page_count": len(document.pages) if hasattr(document, "pages") else 0,
            "language": getattr(document, "language", "Unknown"),
            "creation_date": getattr(document, "creation_date", None),
            "modification_date": getattr(document, "modification_date", None),
            "author": getattr(document, "author", "Unknown"),
            "subject": getattr(document, "subject", "Unknown"),
            "keywords": getattr(document, "keywords", []),
            "has_tables": self._has_tables(document),
            "has_images": self._has_images(document),
            "has_formulas": self._has_formulas(document)
        }
        
        return metadata
    
    def _has_tables(self, document) -> bool:
        """Check if document contains tables"""
        try:
            if hasattr(document, "pages"):
                for page in document.pages:
                    if hasattr(page, "tables") and page.tables:
                        return True
            return False
        except:
            return False
    
    def _has_images(self, document) -> bool:
        """Check if document contains images"""
        try:
            if hasattr(document, "pages"):
                for page in document.pages:
                    if hasattr(page, "images") and page.images:
                        return True
            return False
        except:
            return False
    
    def _has_formulas(self, document) -> bool:
        """Check if document contains mathematical formulas"""
        try:
            if hasattr(document, "pages"):
                for page in document.pages:
                    if hasattr(page, "formulas") and page.formulas:
                        return True
            return False
        except:
            return False
    
    def _chunk_content(self, content: str, config: ChunkingConfig, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Chunk content based on the specified strategy"""
        try:
            if config.strategy == ChunkingStrategy.FIXED_SIZE:
                return self._fixed_size_chunking(content, config)
            elif config.strategy == ChunkingStrategy.SENTENCE_BASED:
                return self._sentence_based_chunking(content, config)
            elif config.strategy == ChunkingStrategy.PARAGRAPH_BASED:
                return self._paragraph_based_chunking(content, config)
            elif config.strategy == ChunkingStrategy.SECTION_BASED:
                return self._section_based_chunking(content, config)
            elif config.strategy == ChunkingStrategy.TABLE_AWARE:
                return self._table_aware_chunking(content, config, metadata)
            else:
                return self._sentence_based_chunking(content, config)
                
        except Exception as e:
            logger.error(f"Chunking failed: {str(e)}")
            return [{"content": content, "chunk_id": 0, "error": str(e)}]
    
    def _fixed_size_chunking(self, content: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
        """Fixed-size chunking strategy"""
        chunks = []
        start = 0
        chunk_id = 0
        
        while start < len(content):
            end = min(start + config.chunk_size, len(content))
            chunk_content = content[start:end]
            
            # Try to break at word boundary
            if end < len(content) and config.respect_sentence_boundaries:
                last_space = chunk_content.rfind(' ')
                if last_space > config.min_chunk_size:
                    end = start + last_space
                    chunk_content = content[start:end]
            
            chunks.append({
                "chunk_id": chunk_id,
                "content": chunk_content.strip(),
                "start_pos": start,
                "end_pos": end,
                "length": len(chunk_content),
                "strategy": "fixed_size"
            })
            
            start = end - config.chunk_overlap
            chunk_id += 1
        
        return chunks
    
    def _sentence_based_chunking(self, content: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
        """Sentence-based chunking strategy"""
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        chunks = []
        current_chunk = ""
        chunk_id = 0
        start_pos = 0
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= config.chunk_size:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "content": current_chunk.strip(),
                        "start_pos": start_pos,
                        "end_pos": start_pos + len(current_chunk),
                        "length": len(current_chunk),
                        "strategy": "sentence_based"
                    })
                    chunk_id += 1
                    start_pos += len(current_chunk)
                
                current_chunk = sentence + " "
        
        # Add remaining content
        if current_chunk:
            chunks.append({
                "chunk_id": chunk_id,
                "content": current_chunk.strip(),
                "start_pos": start_pos,
                "end_pos": start_pos + len(current_chunk),
                "length": len(current_chunk),
                "strategy": "sentence_based"
            })
        
        return chunks
    
    def _paragraph_based_chunking(self, content: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
        """Paragraph-based chunking strategy"""
        paragraphs = content.split('\n\n')
        
        chunks = []
        chunk_id = 0
        start_pos = 0
        
        for paragraph in paragraphs:
            if len(paragraph.strip()) < config.min_chunk_size:
                continue
                
            chunks.append({
                "chunk_id": chunk_id,
                "content": paragraph.strip(),
                "start_pos": start_pos,
                "end_pos": start_pos + len(paragraph),
                "length": len(paragraph),
                "strategy": "paragraph_based"
            })
            
            start_pos += len(paragraph) + 2  # +2 for \n\n
            chunk_id += 1
        
        return chunks
    
    def _section_based_chunking(self, content: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
        """Section-based chunking using headers"""
        # Split by headers (markdown style)
        sections = re.split(r'\n(#{1,6}\s+.+)\n', content)
        
        chunks = []
        chunk_id = 0
        start_pos = 0
        
        for i, section in enumerate(sections):
            if not section.strip():
                continue
                
            # Check if this is a header
            if re.match(r'^#{1,6}\s+', section):
                continue
            
            if len(section.strip()) >= config.min_chunk_size:
                chunks.append({
                    "chunk_id": chunk_id,
                    "content": section.strip(),
                    "start_pos": start_pos,
                    "end_pos": start_pos + len(section),
                    "length": len(section),
                    "strategy": "section_based"
                })
                chunk_id += 1
            
            start_pos += len(section)
        
        return chunks
    
    def _table_aware_chunking(self, content: str, config: ChunkingConfig, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Table-aware chunking strategy"""
        # This is a simplified version - in practice, you'd parse the document structure
        # to identify tables and handle them specially
        
        chunks = []
        chunk_id = 0
        start_pos = 0
        
        # Split by potential table markers
        table_sections = re.split(r'\n(\|.*\|)\n', content)
        
        for section in table_sections:
            if not section.strip():
                continue
            
            # Check if this looks like a table
            if '|' in section and section.count('|') > 2:
                # Handle table as special chunk
                chunks.append({
                    "chunk_id": chunk_id,
                    "content": section.strip(),
                    "start_pos": start_pos,
                    "end_pos": start_pos + len(section),
                    "length": len(section),
                    "strategy": "table_aware",
                    "type": "table"
                })
            else:
                # Regular text chunking
                if len(section.strip()) >= config.min_chunk_size:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "content": section.strip(),
                        "start_pos": start_pos,
                        "end_pos": start_pos + len(section),
                        "length": len(section),
                        "strategy": "table_aware",
                        "type": "text"
                    })
            
            start_pos += len(section)
            chunk_id += 1
        
        return chunks

def lambda_handler(event, context):
    """
    AWS Lambda handler for Docling document processing
    
    Expected event format:
    {
        "document_source": "https://example.com/doc.pdf" or "base64_encoded_content",
        "chunking_strategy": "sentence_based",  # optional
        "chunk_size": 1000,  # optional
        "chunk_overlap": 200,  # optional
        "output_format": "markdown"  # optional
    }
    """
    try:
        # Initialize handler
        handler = DoclingLambdaHandler()
        
        # Extract parameters from event
        document_source = event.get("document_source")
        if not document_source:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "document_source is required"})
            }
        
        # Parse chunking configuration
        chunking_strategy = ChunkingStrategy(event.get("chunking_strategy", "sentence_based"))
        chunk_size = event.get("chunk_size", 1000)
        chunk_overlap = event.get("chunk_overlap", 200)
        output_format = event.get("output_format", "markdown")
        
        chunking_config = ChunkingConfig(
            strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Process document
        result = handler.process_document(
            document_source=document_source,
            chunking_config=chunking_config,
            output_format=output_format
        )
        
        if result.success:
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Document processed successfully",
                    "content": result.content,
                    "chunks": result.chunks,
                    "metadata": result.metadata,
                    "chunking_strategy": chunking_strategy.value,
                    "total_chunks": len(result.chunks)
                })
            }
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": f"Document processing failed: {result.error}"
                })
            }
            
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": f"Internal server error: {str(e)}"
            })
        }
