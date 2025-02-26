from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import logging
from typing import Optional, Dict, List
import re
from openai import OpenAI, AssistantEventHandler
from openai.types.beta.threads import TextDelta, Text
from typing_extensions import override
import tempfile
import os
import datetime

from fastapi.websockets import WebSocketState
from app.config import settings
from app.services.assistant import KnowledgeAssistant

logger = logging.getLogger(__name__)

class TTSAssistantHandler(AssistantEventHandler):
    def __init__(self, client, audio_queue, synthesis_done):
        super().__init__()
        self.client = client
        self.audio_queue = audio_queue
        self.synthesis_done = synthesis_done
        self.current_sentence = ""
        self.processing_tasks = {}  # Maps sentence_id -> asyncio.Task
        self.current_sentence_id = 0  # Just for logging
        
        # New attributes for ordered audio handling
        self.next_sentence_to_send = 1  # Start with the first sentence
        self.stored_audio_chunks = {}  # Maps sentence_id -> list of audio chunks
        
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        
    @override
    def on_text_created(self, text) -> None:
        self.current_sentence = ""
    
    @override
    def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
        self.current_sentence += delta.value
        
        # Check if we have a complete sentence
        if any(end in delta.value for end in ['.', '!', '?']) and len(self.current_sentence.strip()) > 0:
            complete_sentence = self.current_sentence.strip()
            self.current_sentence_id += 1
            sentence_id = self.current_sentence_id
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Sentence {sentence_id} received: {complete_sentence}")
            
            # Process this sentence immediately and ensure it runs right away
            task = asyncio.create_task(self.process_sentence(complete_sentence, sentence_id))
            self.processing_tasks[sentence_id] = task
            
            # Ensure this task gets a chance to run by yielding to the event loop
            asyncio.create_task(self._ensure_immediate_processing(sentence_id, task))
            
            self.current_sentence = ""

    @override
    def on_message_done(self, message) -> None:
        # Process any remaining text
        if len(self.current_sentence.strip()) > 0:
            final_sentence = self.current_sentence.strip()
            self.current_sentence_id += 1
            sentence_id = self.current_sentence_id
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Final sentence {sentence_id} received: {final_sentence}")
            
            # Process the final sentence and ensure it runs immediately
            task = asyncio.create_task(self.process_sentence(final_sentence, sentence_id))
            self.processing_tasks[sentence_id] = task
            
            # Ensure this task gets a chance to run by yielding to the event loop
            asyncio.create_task(self._ensure_immediate_processing(sentence_id, task))
            
        # Wait for all sentences to be processed
        asyncio.create_task(self.wait_for_all_sentences())

    async def wait_for_all_sentences(self):
        """Wait for all sentences to be processed before setting the synthesis_done event."""
        try:
            if self.processing_tasks:
                # Wait for all processing tasks to complete
                await asyncio.gather(*self.processing_tasks.values())
            
            # Make sure all pending audio has been sent
            await self.send_pending_audio()
            
            self.synthesis_done.set()
        except Exception as e:
            logger.error(f"Error in wait_for_all_sentences: {e}", exc_info=True)
            # Ensure the synthesis_done event is set even if there's an error
            self.synthesis_done.set()

    async def process_all_sentences(self):
        """
        Compatibility method for the existing API. 
        We'll wait for all sentences to finish processing.
        """
        try:
            if self.processing_tasks:
                # Wait for all processing tasks to complete
                await asyncio.gather(*self.processing_tasks.values())
            
            # Make sure all pending audio has been sent
            await self.send_pending_audio()
        except Exception as e:
            logger.error(f"Error in process_all_sentences: {e}", exc_info=True)

    async def send_pending_audio(self):
        """
        Check if we can send any pending audio chunks in order.
        This should be called whenever a new sentence is processed.
        """
        while self.next_sentence_to_send in self.stored_audio_chunks:
            sentence_id = self.next_sentence_to_send
            chunks = self.stored_audio_chunks[sentence_id]
            
            for chunk in chunks:
                await self.audio_queue.put(chunk)
            
            # Remove the sent chunks to free memory
            del self.stored_audio_chunks[sentence_id]
            
            # Move to the next sentence
            self.next_sentence_to_send += 1

    async def process_sentence(self, sentence: str, sentence_id: int):
        """
        Convert a sentence to speech using OpenAI TTS and store the chunks
        until they can be sent in order.
        """
        try:
            # Generate speech using OpenAI TTS
            response = await asyncio.to_thread(
                lambda: self.openai_client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    input=sentence
                )
            )
            
            # Create a temporary file and save the audio to it
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_file_path = temp_file.name
                response.write_to_file(temp_file_path)
            
            # Read the entire file into memory
            with open(temp_file_path, "rb") as audio_file:
                audio_data = audio_file.read()
            
            # Clean up the temporary file now that we have the data
            os.unlink(temp_file_path)
            
            # Prepare the audio chunks
            chunk_size = 32768  # 32KB chunks
            chunks = []
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i+chunk_size]
                chunks.append(chunk)
            
            # Store the chunks instead of sending them directly
            self.stored_audio_chunks[sentence_id] = chunks
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Sentence {sentence_id} synthesized ({len(chunks)} chunks)")
            
            # Try to send any pending sentences that are now ready
            # Make this a fire-and-forget task to avoid blocking
            asyncio.create_task(self.send_pending_audio())
            
        except Exception as e:
            logger.error(f"Error processing sentence {sentence_id}: {e}", exc_info=True)
            raise  # Re-raise the exception to ensure it's properly handled upstream

    async def _ensure_immediate_processing(self, sentence_id: int, task):
        """Helper method to ensure immediate processing of sentence tasks."""
        try:
            # Yield control to the event loop to let the task start
            await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"Error in _ensure_immediate_processing for sentence {sentence_id}: {e}", exc_info=True)