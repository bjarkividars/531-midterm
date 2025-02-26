from fastapi import WebSocket, WebSocketDisconnect
import azure.cognitiveservices.speech as speechsdk
import asyncio
import logging
from typing import List, Optional

from fastapi.websockets import WebSocketState
from app.config import settings
from app.services.assistant import KnowledgeAssistant
from app.services.text_to_speech import TTSAssistantHandler
from app.services.pinecone_assistant import PineconeAssistant

region = "eastus"
logger = logging.getLogger("app_logger")

# Configure Azure Speech
speech_config = speechsdk.SpeechConfig(
    subscription=settings.azure_speech_key,
    region="eastus"
)

class TranscriptionResult:
    def __init__(self):
        self.final_outputs: List[str] = []
        self.complete_text: Optional[str] = None

    def add_final_output(self, text: str):
        if text.startswith("FINAL: "):
            text = text[7:]  # Remove the "FINAL: " prefix
        self.final_outputs.append(text)

    def get_complete_text(self) -> str:
        if not self.complete_text:
            self.complete_text = " ".join(self.final_outputs)
        return self.complete_text

# Function to set up the speech recognizer
def setup_speech_recognition(message_queue, recognition_done):
    stream = speechsdk.audio.PushAudioInputStream()
    audio_config = speechsdk.audio.AudioConfig(stream=stream)
    speech_recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config, audio_config=audio_config)

    # Event handlers
    def recognizing_handler(evt):
        logger.debug(f'Recognizing: {evt.result.text}')
        message_queue.put_nowait(f"PARTIAL: {evt.result.text}")

    def recognized_handler(evt):
        logger.debug(f'Recognized: {evt.result.text}')
        message_queue.put_nowait(f"FINAL: {evt.result.text}")

    def session_stopped_handler(evt):
        message_queue.put_nowait("SESSION_STOPPED")
        recognition_done.set()

    def canceled_handler(evt):
        logger.error("Recognition canceled")
        recognition_done.set()

    # Attach handlers to recognizer events
    speech_recognizer.recognizing.connect(recognizing_handler)
    speech_recognizer.recognized.connect(recognized_handler)
    speech_recognizer.session_stopped.connect(session_stopped_handler)
    speech_recognizer.canceled.connect(canceled_handler)

    return speech_recognizer, stream

async def send_messages(websocket, message_queue, transcription_result):
    """Asynchronously send messages from the queue to the WebSocket."""
    try:
        while True:
            message = await message_queue.get()
            if message is None:  # Sentinel to stop
                break
            # Save final results to transcription_result for later processing
            if message.startswith("FINAL: "):
                transcription_result.add_final_output(message)
            await websocket.send_text(message)
    except Exception as e:
        logging.error(f"Error sending messages: {e}")


async def process_with_assistant_and_tts(
    websocket: WebSocket,
    question: str,
    knowledge_assistant: KnowledgeAssistant,
    audio_queue: asyncio.Queue,
    synthesis_done: asyncio.Event
) -> None:
    try:
        # Create conversation thread, etc.
        knowledge_assistant.create_thread()

        # Create TTS handler
        handler = TTSAssistantHandler(
            knowledge_assistant.client,
            audio_queue,
            synthesis_done
        )

        # Send the user question to the language model
        await asyncio.to_thread(
            lambda: knowledge_assistant.ask_and_stream_response(
                question,
                thread_id=knowledge_assistant.current_thread.id,
                handler=handler
            )
        )

        # Process all collected sentences in the main event loop
        await handler.process_all_sentences()

        # -----------------------------------------------------------------
        # Now that the LM stream is done, ensure TTS is also truly finished.
        # We await the event we set in on_complete().
        # -----------------------------------------------------------------
        await handler.synthesis_done.wait()
        print("TTS synthesis done.")
        # Once TTS is done, we can safely enqueue None.
        await audio_queue.put(None)

    except Exception as e:
        logger.error(f"Error processing with assistant and TTS: {e}")
        await websocket.send_text(f"ERROR: {str(e)}")

async def process_with_pinecone_assistant_and_tts(
    websocket: WebSocket,
    question: str,
    pinecone_assistant: PineconeAssistant,
    audio_queue: asyncio.Queue,
    synthesis_done: asyncio.Event
) -> None:
    try:
        # Create TTS handler
        handler = TTSAssistantHandler(
            pinecone_assistant.client,
            audio_queue,
            synthesis_done
        )

        # Send the user question to the language model
        await pinecone_assistant.ask_and_stream_response(
            question,
            handler=handler,
            thread_id=None  # Not used with completions API
        )
        
        # The sentences are already being processed as they come in,
        # and synthesis_done will be set when all sentences are complete.
        
        # Wait for TTS to finish processing all sentences
        await handler.synthesis_done.wait()
        
        # Once TTS is done, we can safely enqueue None to signal the end of the audio stream
        await audio_queue.put(None)

    except Exception as e:
        logger.error(f"Error processing with Pinecone assistant and TTS: {e}", exc_info=True)
        # Still send an error message to the client
        try:
            await websocket.send_text(f"ERROR: {str(e)}")
        except Exception as ws_error:
            logger.error(f"Failed to send error to websocket: {ws_error}")
        
        # Still put None in the queue to unblock the audio sender task
        try:
            await audio_queue.put(None)
        except Exception as queue_error:
            logger.error(f"Failed to put None in audio queue: {queue_error}")

async def websocket_transcribe(websocket: WebSocket, pinecone_assistant: PineconeAssistant):
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    recognition_done = asyncio.Event()
    message_queue = asyncio.Queue()
    transcription_result = TranscriptionResult()
    audio_queue_tts = asyncio.Queue()  # Queue for TTS audio chunks
    synthesis_done_event = asyncio.Event()  # Event for TTS completion

    speech_recognizer, stream = setup_speech_recognition(
        message_queue, recognition_done
    )

    # Start sending partial/final transcription messages
    message_sender_task = asyncio.create_task(
        send_messages(websocket, message_queue, transcription_result)
    )

    audio_sender_task_tts = None  # Will start later if needed

    try:
        speech_recognizer.start_continuous_recognition()

        while True:
            try:
                data = await websocket.receive()

                # Check if it's a text message (command) or bytes (audio)
                if "text" in data:
                    command = data["text"]
                    if command == "STOP_DISCARD":
                        logger.info("Received stop command with discard")
                        break
                    elif command == "STOP_PROCESS":
                        logger.info("Received stop command with process")
                        # Wait for all partial/final messages to be sent
                        speech_recognizer.stop_continuous_recognition()
                        await recognition_done.wait()
                        await message_queue.put(None)
                        await message_sender_task

                        # Now get the complete text
                        complete_text = transcription_result.get_complete_text()
                        logger.info(f"Complete transcription text: {complete_text[:50]}...")
                        await websocket.send_text(f"COMPLETE_TRANSCRIPTION: {complete_text}")

                        # Process with Pinecone assistant and TTS if available
                        if pinecone_assistant and complete_text.strip():
                            logger.info("Processing with assistant and TTS")
                            
                            audio_sender_task_tts = asyncio.create_task(
                                send_audio_chunks(websocket, audio_queue_tts)
                            )
                            
                            # TTS + generative response with Pinecone assistant
                            await process_with_pinecone_assistant_and_tts(
                                websocket,
                                complete_text,
                                pinecone_assistant,
                                audio_queue_tts,
                                synthesis_done_event
                            )
                        break
                    elif command == "CHUNKS_DONE":
                        logger.info("Received 'CHUNKS_DONE' signal from client")
                        break
                elif "bytes" in data:
                    audio_chunk = data["bytes"]
                    if audio_chunk:
                        stream.write(audio_chunk)
                    else:
                        logger.info("Received empty audio chunk")
                        break

            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                break

    except Exception as e:
        logger.error(f"Error during WebSocket transcription: {e}")
    finally:
        # Make sure we stop the speech recognizer and finish message sending
        if not recognition_done.is_set():
            speech_recognizer.stop_continuous_recognition()
            await recognition_done.wait()
            await message_queue.put(None)
            await message_sender_task

        if audio_sender_task_tts:
            # Wait for the audio sender to drain its queue
            await audio_sender_task_tts

        stream.close()

        try:
            await websocket.send_text("DONE")
        except Exception as e:
            logger.error(f"Error sending 'DONE': {e}")


async def send_audio_chunks(websocket: WebSocket, audio_queue: asyncio.Queue):
    """Send audio chunks from the queue to the WebSocket."""
    chunk_counter = 0
    try:
        while True:
            item = await audio_queue.get()
            
            # Check if this is the end of stream marker
            if item is None:
                # Send a final message to indicate all audio has been sent
                await websocket.send_json({"type": "audio_complete"})
                break

            # Skip any JSON messages/markers
            if isinstance(item, dict):
                continue
            
            # This is a regular audio chunk - send it directly
            chunk_counter += 1
            await websocket.send_bytes(item)
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error sending audio chunks: {e}", exc_info=True)
    finally:
        logger.info(f'Sent {chunk_counter} audio chunks')