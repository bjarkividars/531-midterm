from openai import OpenAI, AssistantEventHandler
from openai.types.beta.threads import TextDelta, Text
from typing_extensions import override
import os
import glob
import json
import asyncio
from typing import Optional, List, Dict, Any, Callable
import datetime
from fastapi import FastAPI

from app.config import settings
from app.services.pinecone_vector_store import PineconeVectorStore


class StreamingCompletionHandler:
    """
    A handler for streaming completions from the OpenAI API.
    This mimics the functionality of AssistantEventHandler but for completions.
    """

    def __init__(self, assistant_handler: AssistantEventHandler):
        """
        Initialize with an AssistantEventHandler to delegate events to.

        Args:
            assistant_handler: The AssistantEventHandler to delegate events to
        """
        self.assistant_handler = assistant_handler
        self.current_text = ""

    def handle_chunk(self, chunk):
        """
        Handle a chunk from the streaming completion.

        Args:
            chunk: A chunk from the OpenAI streaming completion
        """
        if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
            delta_content = chunk.choices[0].delta.content
            if delta_content:
                # Create a TextDelta-like object
                delta = type('TextDelta', (), {'value': delta_content})

                # Create a Text-like object for the snapshot
                self.current_text += delta_content
                snapshot = type('Text', (), {'value': self.current_text})

                # Call the on_text_delta method of the assistant handler
                self.assistant_handler.on_text_delta(delta, snapshot)

    def handle_completion(self):
        """
        Handle the completion of the streaming response.
        """
        # Create a message-like object
        message = type('Message', (), {'content': [
                       {'text': {'value': self.current_text}}]})

        # Call the on_message_done method of the assistant handler
        self.assistant_handler.on_message_done(message)


class PineconeAssistant:
    """
    A knowledge assistant that uses Pinecone for vector storage and retrieval,
    and OpenAI's completions API for generating responses.
    """

    def __init__(self, app: Optional[FastAPI] = None):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.vector_store = None
        self.model = "gpt-4.1"
        self.base_system_prompt = """
            Your response will be spoken aloud by the presenter during a live presentation.

            Your primary goal is to provide clear, natural, and confident answers that sound like something a well-prepared speaker would say on stage. Keep your tone conversational, concise, and helpful — avoid overly technical, robotic, or formal phrasing.

            You will be given relevant context from a knowledge base. Use this to craft accurate answers. Do not mention the context, source, or that you were given information — just speak as if you know the answer.

            If the context does not contain enough information to answer confidently, just say "That's a great question. I don't have that information at the top of my head but I'll get back to you on that." Never fabricate certainty.

            Summary of rules:
            - Responses must sound natural when spoken aloud
            - Do not reference context or data sources
            - Be helpful, clear, and confident
            - Use guesstimates only when needed, and label them clearly

            Always aim to support the presenter — your answer should help them shine.
            """

        # Placeholder for additional presentation context
        self.presentation_context = ""

        # Store reference to the FastAPI app for accessing app.state
        self.app = app

    def get_system_prompt(self) -> str:
        """
        Get the complete system prompt including presentation context if available.
        """
        if not self.presentation_context:
            return self.base_system_prompt

        return f"{self.base_system_prompt}\n\nAdditional context about this specific presentation:\n{self.presentation_context}"

    async def initialize_async(self):
        """Initialize the parts that need to be done asynchronously."""
        # Initialize Pinecone vector store
        self.vector_store = PineconeVectorStore(index_name="knowledge-base")
        return self

    @classmethod
    async def create(cls, app: Optional[FastAPI] = None):
        """Factory method to create and initialize the assistant asynchronously."""
        assistant = cls(app)
        await assistant.initialize_async()
        return assistant

    async def upload_knowledge_files(self, directory_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload all files from the knowledge directory to the Pinecone vector store.

        Args:
            directory_path: Optional path to the knowledge directory.
                           If None, uses the default 'knowledge' directory.

        Returns:
            Dictionary with upload statistics
        """
        if not self.vector_store:
            await self.initialize_async()
        return await self.vector_store.upload_knowledge_directory(directory_path)

    async def ask_and_stream_response(self, question: str, handler: AssistantEventHandler, thread_id: Optional[str] = None) -> None:
        """
        Ask a question to the assistant and stream the response using completions API.

        This method:
        1. Retrieves relevant context from Pinecone
        2. Creates a prompt with the context and question
        3. Streams the response through the provided handler

        Args:
            question: The question to ask
            handler: Event handler for streaming the response
            thread_id: Optional thread ID (not used with completions API, kept for compatibility)
        """
        if not self.vector_store:
            await self.initialize_async()

        # Create a handler for streaming completions
        completion_handler = StreamingCompletionHandler(handler)

        # Notify that text creation has started
        if hasattr(handler, 'on_text_created'):
            handler.on_text_created(None)

        try:
            # Retrieve relevant context from Pinecone
            context_results = await self.vector_store.query(question, top_k=5)

            # Format the context
            context_text = "Here is relevant information from the knowledge base:\n\n"
            for i, result in enumerate(context_results):
                context_text += f"[Document: {result['source']}, Chunk: {result['chunk_id']}]\n"
                context_text += f"{result['text']}\n\n"

            # Create messages for the completions API
            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": f"{context_text}\n\nUser question: {question}"}
            ]

            # Stream the response using the completions API
            stream = await asyncio.to_thread(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True
                )
            )

            # Process the streaming response
            for chunk in stream:
                completion_handler.handle_chunk(chunk)
                # Small yield to allow other async tasks to run
                await asyncio.sleep(0)

            # Signal that the message is complete
            completion_handler.handle_completion()

        except Exception as e:
            print(f"Error in ask_and_stream_response: {e}")
            raise

    def get_output_websocket(self):
        """
        Get the output websocket from app state if available.

        Returns:
            WebSocket: The output websocket or None if not available
        """
        if self.app and hasattr(self.app.state, 'output_websocket'):
            return self.app.state.output_websocket
        return None
