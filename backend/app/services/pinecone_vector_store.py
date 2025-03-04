import os
import glob
import uuid
import logging
import time
from typing import List, Dict, Any, Optional
import asyncio

import pinecone
from pinecone import Pinecone, ServerlessSpec
import openai
from openai import OpenAI
import tiktoken
import numpy as np
import PyPDF2

from app.config import settings

logger = logging.getLogger(__name__)


class PineconeVectorStore:
    """
    A custom vector store implementation using Pinecone.
    Handles chunking documents and uploading them to Pinecone.
    """

    def __init__(self, index_name: str = "knowledge-base"):
        """
        Initialize the Pinecone vector store.

        Args:
            index_name: Name of the Pinecone index to use
        """
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.index_name = index_name
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dimensions = 1536  # Dimensions for text-embedding-3-small
        self.chunk_size = 1000  # Target size for text chunks
        self.chunk_overlap = 200  # Overlap between chunks
        self.pc = None
        self.index = None

        # Initialize Pinecone client and index
        self._initialize_pinecone()

    def _initialize_pinecone(self):
        """Initialize the Pinecone client and create index if it doesn't exist."""
        try:
            # Initialize Pinecone client
            self.pc = Pinecone(api_key=settings.pinecone_api_key)

            # Check if index exists
            existing_indexes = [index.name for index in self.pc.list_indexes()]

            if self.index_name not in existing_indexes:
                logger.info(f"Creating new Pinecone index: {self.index_name}")
                # Create a new serverless index
                self.pc.create_index(
                    name=self.index_name,
                    dimension=self.embedding_dimensions,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
                logger.info(
                    f"Waiting for index {self.index_name} to be ready...")
                # Wait for index to be ready
                while not self.pc.describe_index(self.index_name).status["ready"]:
                    time.sleep(1)

            # Connect to the index
            self.index = self.pc.Index(self.index_name)
            logger.info(f"Connected to Pinecone index: {self.index_name}")

        except Exception as e:
            logger.error(f"Error initializing Pinecone: {e}", exc_info=True)
            raise

    def _get_token_count(self, text: str) -> int:
        """
        Count the number of tokens in a text string.

        Args:
            text: The text to count tokens for

        Returns:
            Number of tokens
        """
        encoding = tiktoken.encoding_for_model("gpt-4")
        return len(encoding.encode(text))

    def _chunk_text(self, text: str, filename: str) -> List[Dict[str, Any]]:
        """
        Split text into chunks with metadata.

        Args:
            text: The text to chunk
            filename: The source filename for metadata

        Returns:
            List of chunk dictionaries with text and metadata
        """
        # Split text into paragraphs
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        current_size = 0

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            paragraph_size = self._get_token_count(paragraph)

            # If paragraph is too big on its own, split it into sentences
            if paragraph_size > self.chunk_size:
                sentences = paragraph.replace(". ", ".\n").split("\n")
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    sentence_size = self._get_token_count(sentence)

                    if current_size + sentence_size > self.chunk_size:
                        if current_chunk:
                            chunks.append({
                                "text": current_chunk.strip(),
                                "metadata": {
                                    "source": filename,
                                    "chunk_id": str(len(chunks))
                                }
                            })
                        current_chunk = sentence
                        current_size = sentence_size
                    else:
                        current_chunk += " " + sentence
                        current_size += sentence_size
            else:
                # If adding this paragraph exceeds chunk size, start a new chunk
                if current_size + paragraph_size > self.chunk_size:
                    if current_chunk:
                        chunks.append({
                            "text": current_chunk.strip(),
                            "metadata": {
                                "source": filename,
                                "chunk_id": str(len(chunks))
                            }
                        })
                    current_chunk = paragraph
                    current_size = paragraph_size
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + paragraph
                    else:
                        current_chunk = paragraph
                    current_size += paragraph_size

        # Add the last chunk if it exists
        if current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "metadata": {
                    "source": filename,
                    "chunk_id": str(len(chunks))
                }
            })

        return chunks

    async def _get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a text using OpenAI's embedding API.

        Args:
            text: The text to embed

        Returns:
            Embedding vector
        """
        try:
            # Use asyncio.to_thread to run the synchronous OpenAI call in a thread
            response = await asyncio.to_thread(
                lambda: self.openai_client.embeddings.create(
                    model=self.embedding_model,
                    input=text
                )
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error getting embedding: {e}", exc_info=True)
            raise

    async def upload_file(self, file_path: str) -> Dict[str, Any]:
        """
        Process a file, chunk it, and upload to Pinecone.

        Args:
            file_path: Path to the file to process

        Returns:
            Dictionary with upload statistics
        """
        try:
            # Get filename for metadata
            filename = os.path.basename(file_path)
            file_extension = os.path.splitext(filename)[1].lower()

            # Handle different file types
            if file_extension == '.pdf':
                try:
                    # Import PyPDF2 for PDF processing

                    # Read PDF file
                    with open(file_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        content = ""

                        # Extract text from each page
                        for page_num in range(len(pdf_reader.pages)):
                            page = pdf_reader.pages[page_num]
                            content += page.extract_text() + "\n\n"

                except ImportError:
                    logger.error(
                        "PyPDF2 not installed. Please install it to process PDF files.")
                    return {
                        "status": "error",
                        "file": filename,
                        "error": "PyPDF2 not installed. Please install it to process PDF files."
                    }
            else:
                # Default to text file reading for non-PDF files
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    # Try with a different encoding if UTF-8 fails
                    try:
                        with open(file_path, 'r', encoding='latin-1') as f:
                            content = f.read()
                    except Exception as e:
                        logger.error(f"Error reading file {filename}: {e}")
                        return {
                            "status": "error",
                            "file": filename,
                            "error": f"Unable to read file: {str(e)}"
                        }

            # Skip empty content
            if not content or content.strip() == "":
                logger.warning(
                    f"File {filename} is empty or contains no extractable text.")
                return {
                    "status": "warning",
                    "file": filename,
                    "error": "File is empty or contains no extractable text."
                }

            # Chunk the text
            chunks = self._chunk_text(content, filename)
            logger.info(f"Created {len(chunks)} chunks from {filename}")

            # Process chunks in batches to avoid rate limits
            vectors_to_upsert = []
            batch_size = 100

            for i, chunk in enumerate(chunks):
                # Get embedding for chunk
                embedding = await self._get_embedding(chunk["text"])

                # Create vector record
                vector_id = f"{filename}_{chunk['metadata']['chunk_id']}"
                vector_record = {
                    "id": vector_id,
                    "values": embedding,
                    "metadata": {
                        "text": chunk["text"],
                        "source": chunk["metadata"]["source"],
                        "chunk_id": chunk["metadata"]["chunk_id"]
                    }
                }

                vectors_to_upsert.append(vector_record)

                # Upsert in batches
                if len(vectors_to_upsert) >= batch_size or i == len(chunks) - 1:
                    await asyncio.to_thread(
                        lambda: self.index.upsert(vectors=vectors_to_upsert)
                    )
                    logger.info(
                        f"Upserted batch of {len(vectors_to_upsert)} vectors")
                    vectors_to_upsert = []

            return {
                "status": "success",
                "file": filename,
                "chunks_processed": len(chunks)
            }

        except Exception as e:
            logger.error(
                f"Error uploading file {file_path}: {e}", exc_info=True)
            return {
                "status": "error",
                "file": os.path.basename(file_path),
                "error": str(e)
            }

    async def upload_knowledge_directory(self, directory_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload all files from a directory to the vector store.

        Args:
            directory_path: Path to directory containing knowledge files.
                           If None, uses the default 'knowledge' directory.

        Returns:
            Dictionary with upload statistics
        """
        if directory_path is None:
            directory_path = os.path.join(os.getcwd(), "knowledge")

        file_paths = glob.glob(os.path.join(directory_path, "*"))

        if not file_paths:
            raise ValueError(
                f"No files found in the directory: {directory_path}")

        logger.info(
            f"Uploading {len(file_paths)} files from '{directory_path}' to Pinecone")

        results = []
        for file_path in file_paths:
            result = await self.upload_file(file_path)
            results.append(result)

        success_count = sum(1 for r in results if r["status"] == "success")

        return {
            "status": "completed",
            "total_files": len(file_paths),
            "successful_uploads": success_count,
            "failed_uploads": len(file_paths) - success_count,
            "details": results
        }

    async def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Query the vector store for similar documents.

        Args:
            query_text: The query text
            top_k: Number of results to return

        Returns:
            List of matching documents with similarity scores
        """
        try:
            # Get embedding for query
            query_embedding = await self._get_embedding(query_text)

            # Query Pinecone
            query_results = await asyncio.to_thread(
                lambda: self.index.query(
                    vector=query_embedding,
                    top_k=top_k,
                    include_metadata=True
                )
            )

            # Format results
            results = []
            for match in query_results.matches:
                results.append({
                    "score": match.score,
                    "text": match.metadata["text"],
                    "source": match.metadata["source"],
                    "chunk_id": match.metadata["chunk_id"]
                })

            return results

        except Exception as e:
            logger.error(f"Error querying vector store: {e}", exc_info=True)
            raise

    async def delete_file_vectors(self, filename: str) -> Dict[str, Any]:
        """
        Delete all vector embeddings associated with a specific file.
        
        Args:
            filename: Name of the file whose vectors should be deleted
            
        Returns:
            Dictionary with deletion statistics
        """
        try:
            if not self.index:
                await self.initialize_async()
                
            # Get all vector IDs with metadata.source matching the filename
            # First, we need to find all the vectors that have this filename
            fetch_response = await asyncio.to_thread(
                lambda: self.index.query(
                    vector=[0] * self.embedding_dimensions,  # Dummy vector
                    top_k=10000,  # Large number to get all potential matches
                    include_metadata=True,
                    filter={"source": {"$eq": filename}}
                )
            )
            
            # Extract IDs of vectors to delete
            vector_ids = [match.id for match in fetch_response.matches]
            
            if not vector_ids:
                logger.info(f"No vectors found for file '{filename}'")
                return {
                    "deleted": False,
                    "message": f"No vectors found for file '{filename}'",
                    "count": 0
                }
                
            # Delete the vectors
            delete_response = await asyncio.to_thread(
                lambda: self.index.delete(ids=vector_ids)
            )
            
            logger.info(f"Deleted {len(vector_ids)} vectors for file '{filename}'")
            return {
                "deleted": True,
                "message": f"Deleted {len(vector_ids)} vectors for file '{filename}'",
                "count": len(vector_ids)
            }
            
        except Exception as e:
            logger.error(f"Error deleting vectors for file '{filename}': {e}", exc_info=True)
            raise
