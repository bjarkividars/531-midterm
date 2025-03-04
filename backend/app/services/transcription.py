from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import logging
from typing import List, Optional

from fastapi.websockets import WebSocketState
from app.config import settings
from app.services.pinecone_assistant import PineconeAssistant
from app.services.speech_recognition import create_speech_manager
from openai import AssistantEventHandler
from openai.types.beta.threads import TextDelta, Text
from typing_extensions import override

logger = logging.getLogger("app_logger")

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

async def process_with_pinecone_assistant_text_only(
    websocket: WebSocket,
    question: str,
    pinecone_assistant: PineconeAssistant
) -> None:
    """
    Process the user question with the Pinecone assistant and send text responses
    directly to the websocket for teleprompter-style display.
    """
    try:
        # Create a custom handler that sends text directly to the websocket
        class WebSocketTextHandler(AssistantEventHandler):
            def __init__(self, websocket):
                super().__init__()
                self.websocket = websocket
                self.current_text = ""
                self.is_connection_open = True
                
            @override
            def on_text_created(self, text) -> None:
                self.current_text = ""
            
            @override
            def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
                # Send each piece of text as it comes in
                if delta.value and self.is_connection_open:
                    # Create a task to send the text without blocking
                    asyncio.create_task(self._safe_send_json({
                        "type": "text_delta",
                        "text": delta.value
                    }))
            
            @override
            def on_message_done(self, message) -> None:
                # Signal that we're done
                if self.is_connection_open:
                    asyncio.create_task(self._safe_send_json({
                        "type": "text_complete"
                    }))
            
            async def _safe_send_json(self, data: dict) -> None:
                try:
                    if self.websocket.client_state == WebSocketState.CONNECTED:
                        await self.websocket.send_json(data)
                except RuntimeError as e:
                    logger.error(f"WebSocket error: {e}")
                    self.is_connection_open = False
                except Exception as e:
                    logger.error(f"Error sending WebSocket message: {e}")
                    self.is_connection_open = False
        
        # Create the handler
        handler = WebSocketTextHandler(websocket)
        
        # Send message to client that we're starting to process
        await websocket.send_json({
            "type": "processing_start",
            "message": "Processing your question..."
        })
        
        # Send the user question to the language model with our custom handler
        await pinecone_assistant.ask_and_stream_response(
            question,
            handler=handler,
            thread_id=None  # Not used with completions API
        )
        
    except Exception as e:
        logger.error(f"Error processing with Pinecone assistant (text only): {e}", exc_info=True)
        # Send error message to the client
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error: {str(e)}"
                })
        except Exception as ws_error:
            logger.error(f"Failed to send error to websocket: {ws_error}")

async def websocket_transcribe(websocket: WebSocket, pinecone_assistant: PineconeAssistant):
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    recognition_done = asyncio.Event()
    message_queue = asyncio.Queue()
    transcription_result = TranscriptionResult()

    # Create a message callback that puts messages on the queue
    def message_callback(message):
        message_queue.put_nowait(message)

    # Create the speech recognition manager
    speech_manager = create_speech_manager(
        message_callback=message_callback,
        recognition_done_event=recognition_done
    )

    # Start sending partial/final transcription messages
    message_sender_task = asyncio.create_task(
        send_messages(websocket, message_queue, transcription_result)
    )

    try:
        speech_manager.start_recognition()

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
                        speech_manager.stop_recognition()
                        await recognition_done.wait()
                        await message_queue.put(None)
                        await message_sender_task

                        # Now get the complete text
                        complete_text = transcription_result.get_complete_text()
                        logger.info(f"Complete transcription text: {complete_text[:50]}...")
                        await websocket.send_text(f"COMPLETE_TRANSCRIPTION: {complete_text}")

                        # Process with Pinecone assistant if available
                        if pinecone_assistant and complete_text.strip():
                            logger.info("Processing with assistant (text only)")
                            
                            # Use our text-only processing function
                            await process_with_pinecone_assistant_text_only(
                                websocket,
                                complete_text,
                                pinecone_assistant
                            )
                        break
                    elif command == "CHUNKS_DONE":
                        logger.info("Received 'CHUNKS_DONE' signal from client")
                        break
                elif "bytes" in data:
                    audio_chunk = data["bytes"]
                    if audio_chunk:
                        speech_manager.process_audio_chunk(audio_chunk)
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
            speech_manager.stop_recognition()
            await recognition_done.wait()
            await message_queue.put(None)
            await message_sender_task

        speech_manager.close()

        try:
            await websocket.send_json({"type": "DONE"})
        except Exception as e:
            logger.error(f"Error sending 'DONE': {e}")