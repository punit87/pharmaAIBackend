import json
import os
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

def lambda_handler(event, context):
    """
    AWS Lambda handler for RAG-Anything
    """
    try:
        # Parse the event
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            query = body.get('query', '')
            document = body.get('document', '')
        else:
            query = event.get('query', '')
            document = event.get('document', '')
        
        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Query parameter is required'})
            }
        
        # Initialize RAG-Anything
        config = RAGAnythingConfig(
            working_dir="/tmp/rag_storage",
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        )
        
        # Set up LLM functions
        def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return openai_complete_if_cache(
                "gpt-4o-mini",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=os.environ.get('OPENAI_API_KEY'),
                **kwargs,
            )
        
        embedding_func = EmbeddingFunc(
            embedding_dim=3072,
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts,
                model="text-embedding-3-large",
                api_key=os.environ.get('OPENAI_API_KEY'),
            ),
        )
        
        rag = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        
        # Process document if provided
        if document:
            # This would need to be implemented based on your document processing needs
            pass
        
        # Query the RAG system
        result = rag.query(query, mode="hybrid")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'query': query,
                'answer': result,
                'requestId': context.aws_request_id
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Query processing failed',
                'message': str(e)
            })
        }
