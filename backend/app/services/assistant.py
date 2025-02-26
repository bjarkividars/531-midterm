from openai import OpenAI, AssistantEventHandler
from openai.types.beta.threads import TextDelta, Text
from typing_extensions import override
import os
import glob
from typing import Optional, List

from app.config import settings


class KnowledgeAssistant:
    def __init__(self):
        print('this is the key', settings.openai_api_key)
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.assistant = None
        self.vector_store = None
        self.current_thread = None
        self._initialize_assistant()

    def _initialize_assistant(self):
        """Initialize the OpenAI assistant and vector store."""
        self.vector_store = self.client.beta.vector_stores.create(
            name="Knowledge Base")

        self.assistant = self.client.beta.assistants.create(
            name="Question Answering Assistant",
            instructions="You are a helpful assistant that can answer questions about the user's data. You are given a transcript of a question. You need to answer the question based on the information in the knowledge base.",
            model="gpt-4o",
            tools=[{"type": "file_search"}]
        )

    def upload_knowledge_files(self) -> dict:
        """
        Upload all files from the knowledge directory to the OpenAI vector store.
        Returns the file batch object containing status and file counts.
        """
        knowledge_dir = os.path.join(os.getcwd(), "knowledge")
        file_paths = glob.glob(os.path.join(knowledge_dir, "*"))

        if not file_paths:
            raise ValueError("No files found in the knowledge directory")

        # Print the number of files found and the directory path
        print(
            f"Uploading {len(file_paths)} file(s) from '{knowledge_dir}' to the vector store...")

        file_streams = [open(path, "rb") for path in file_paths]

        try:
            file_batch = self.client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=self.vector_store.id,
                files=file_streams
            )

            # Print the upload status and file counts returned from the API
            print(f"Upload complete. Status: {file_batch.status}")
            print(f"File counts: {file_batch.file_counts}")

            # Update assistant with the vector store
            self.assistant = self.client.beta.assistants.update(
                assistant_id=self.assistant.id,
                tool_resources={"file_search": {
                    "vector_store_ids": [self.vector_store.id]}}
            )

            return {
                "status": file_batch.status,
                "file_counts": file_batch.file_counts
            }
        finally:
            for stream in file_streams:
                stream.close()

    def create_thread(self):
        """Create a new conversation thread."""
        self.current_thread = self.client.beta.threads.create()
        return self.current_thread
    
    def test_basic_model(self, question: str):
        """Test the basic model."""
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": question}],
            stream=True
        )
        for chunk in response:
            print(chunk.choices[0].delta.content)

    def ask_and_stream_response(self, question: str, handler: AssistantEventHandler, thread_id: Optional[str] = None) -> None:
        """
        Ask a question to the assistant and stream the response.

        Args:
            question: The question to ask
            thread_id: Optional thread ID. If not provided, creates a new thread.
        """
        self.test_basic_model(question)
        
        print('asking question')
        if not thread_id and not self.current_thread:
            self.create_thread()
        print('thread_id', thread_id)

        thread_id = thread_id or self.current_thread.id
        print(
            'creating user message'
        )
        # Add the user's message to the thread
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=question
        )
        print('created user message')
        # Stream the response with our event handler
        with self.client.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id=self.assistant.id,
            event_handler=handler,
        ) as stream:
            stream.until_done()
