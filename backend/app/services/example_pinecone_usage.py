import asyncio
import logging
import os
import sys

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.pinecone_vector_store import PineconeVectorStore
from app.services.pinecone_assistant import PineconeAssistant
from app.services.text_to_speech import TTSAssistantHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def upload_knowledge_example():
    """Example of uploading knowledge files to Pinecone."""
    vector_store = PineconeVectorStore(index_name="knowledge-base")
    
    # Specify the directory containing your knowledge files
    knowledge_dir = os.path.join(os.getcwd(), "knowledge")
    
    # Create the directory if it doesn't exist
    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)
        
        # Create a sample knowledge file for testing
        with open(os.path.join(knowledge_dir, "sample.txt"), "w") as f:
            f.write("""
            # Sample Knowledge Document
            
            This is a sample document that demonstrates how the Pinecone vector store works.
            
            ## Key Features
            
            1. Efficient document chunking
            2. Semantic search using OpenAI embeddings
            3. Fast retrieval with Pinecone
            
            ## Use Cases
            
            The Pinecone vector store is ideal for:
            - Question answering systems
            - Document retrieval
            - Semantic search applications
            
            ## Technical Details
            
            The system uses OpenAI's text-embedding-3-small model to create embeddings,
            which are then stored in Pinecone for efficient retrieval.
            """)
    
    # Upload the knowledge files
    result = await vector_store.upload_knowledge_directory(knowledge_dir)
    logger.info(f"Upload result: {result}")
    
    return vector_store

async def query_example(vector_store):
    """Example of querying the Pinecone vector store."""
    # Query the vector store
    query = "What are the key features of the system?"
    results = await vector_store.query(query, top_k=3)
    
    logger.info(f"Query: {query}")
    logger.info(f"Found {len(results)} results:")
    
    for i, result in enumerate(results):
        logger.info(f"Result {i+1}:")
        logger.info(f"  Score: {result['score']}")
        logger.info(f"  Source: {result['source']}")
        logger.info(f"  Text: {result['text'][:100]}...")

class SimpleEventHandler(TTSAssistantHandler):
    """A simplified event handler for demonstration purposes."""
    
    def __init__(self):
        # Create dummy queues and events for the parent class
        self.audio_queue = asyncio.Queue()
        self.synthesis_done = asyncio.Event()
        self.sentences_to_process = []
        
    async def process_all_sentences(self):
        """Override to just print the sentences instead of processing them."""
        logger.info(f"Would process {len(self.sentences_to_process)} sentences:")
        for sentence in self.sentences_to_process:
            logger.info(f"  - {sentence}")
        self.synthesis_done.set()

async def assistant_example():
    """Example of using the PineconeAssistant."""
    # Create and initialize the assistant
    assistant = await PineconeAssistant.create()
    
    # Upload knowledge files
    await assistant.upload_knowledge_files()
    
    # Create a thread
    assistant.create_thread()
    
    # Create a simple event handler
    handler = SimpleEventHandler()
    
    # Ask a question
    question = "What are the key features and use cases of the system?"
    logger.info(f"Asking: {question}")
    
    # Get the response
    await assistant.ask_and_stream_response(question, handler)
    
    # Wait for the handler to finish
    await handler.synthesis_done.wait()
    
    logger.info("Assistant response complete")

async def main():
    """Run the examples."""
    logger.info("Starting Pinecone vector store example")
    
    # Example 1: Upload knowledge files
    vector_store = await upload_knowledge_example()
    
    # Example 2: Query the vector store
    await query_example(vector_store)
    
    # Example 3: Use the assistant
    await assistant_example()
    
    logger.info("Examples completed")

if __name__ == "__main__":
    asyncio.run(main()) 