import azure.cognitiveservices.speech as speechsdk
import asyncio
import logging
from typing import Callable, Optional, Any
from app.config import settings
from fastapi import WebSocket
from fastapi.websockets import WebSocketState

logger = logging.getLogger("app_logger")

# Configure Azure Speech
speech_config = speechsdk.SpeechConfig(
    subscription=settings.azure_speech_key,
    region="eastus"
)

class SpeechRecognitionManager:
    """
    A reusable speech recognition manager that can be used by both 
    the transcription and teleprompter components.
    """
    def __init__(self, 
                 message_callback: Optional[Callable[[str], Any]] = None,
                 recognition_done_event: Optional[asyncio.Event] = None,
                 transcription_result = None,
                 output_websocket: Optional[WebSocket] = None):
        """
        Initialize the speech recognition manager.
        
        Args:
            message_callback: (Legacy) Callback function to receive recognition messages
            recognition_done_event: Optional event to signal when recognition is done
            transcription_result: Optional TranscriptionResult to update directly
            output_websocket: Optional WebSocket to send messages directly to
        """
        self.message_callback = message_callback
        self.recognition_done_event = recognition_done_event or asyncio.Event()
        self.transcription_result = transcription_result
        self.output_websocket = output_websocket
        
        # Save the current event loop for use in callbacks
        self.loop = asyncio.get_event_loop()
        
        audio_format = speechsdk.audio.AudioStreamFormat(samples_per_second=44100, bits_per_sample=16, channels=1)
        self.stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.stream)
        self.speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, 
            audio_config=self.audio_config
        )
        
        # Set up event handlers
        self.setup_event_handlers()
    
    async def _send_json_to_websocket(self, data: dict):
        """
        Helper to safely send JSON to the output websocket.
        """
        if not self.output_websocket:
            return
            
        try:
            if self.output_websocket.client_state == WebSocketState.CONNECTED:
                await self.output_websocket.send_json(data)
                logger.debug(f"Sent message to output websocket: {data.get('type')}")
        except Exception as e:
            logger.error(f"Error sending message to websocket: {e}", exc_info=True)
    
    def setup_event_handlers(self):
        """Set up the event handlers for the speech recognizer."""
        def recognizing_handler(evt):
            partial_text = evt.result.text
            logger.debug(f'Recognizing: {partial_text}')
            
            # Handle the partial transcription result via message callback
            if self.message_callback:
                self.message_callback(f"PARTIAL: {partial_text}")
                
            # If we have an output websocket, send directly to it using run_coroutine_threadsafe
            if self.output_websocket:
                try:
                    # Use run_coroutine_threadsafe to properly run the coroutine from this thread
                    asyncio.run_coroutine_threadsafe(
                        self._send_json_to_websocket({
                            "type": "partial_transcription",
                            "text": partial_text
                        }), 
                        self.loop
                    )
                except Exception as e:
                    logger.error(f"Error scheduling partial transcription send: {e}", exc_info=True)

        def recognized_handler(evt):
            final_text = evt.result.text
            logger.debug(f'Recognized: {final_text}')
            
            # Handle the final transcription via message callback
            if self.message_callback:
                self.message_callback(f"FINAL: {final_text}")
                
            # Update transcription result if available
            if self.transcription_result:
                self.transcription_result.add_final_output(final_text)
                
            # Send to output websocket if available
            if self.output_websocket:
                try:
                    # Use run_coroutine_threadsafe to properly run the coroutine from this thread
                    asyncio.run_coroutine_threadsafe(
                        self._send_json_to_websocket({
                            "type": "final_transcription_segment",
                            "text": final_text
                        }), 
                        self.loop
                    )
                except Exception as e:
                    logger.error(f"Error scheduling final transcription send: {e}", exc_info=True)

        def session_stopped_handler(evt):
            if self.message_callback:
                self.message_callback("SESSION_STOPPED")
            self.recognition_done_event.set()

        def canceled_handler(evt):
            logger.error("Recognition canceled")
            self.recognition_done_event.set()

        # Attach handlers to recognizer events
        self.speech_recognizer.recognizing.connect(recognizing_handler)
        self.speech_recognizer.recognized.connect(recognized_handler)
        self.speech_recognizer.session_stopped.connect(session_stopped_handler)
        self.speech_recognizer.canceled.connect(canceled_handler)
    
    def start_recognition(self):
        """Start continuous recognition."""
        self.speech_recognizer.start_continuous_recognition()
    
    def stop_recognition(self):
        """Stop continuous recognition."""
        self.speech_recognizer.stop_continuous_recognition()
    
    def process_audio_chunk(self, audio_chunk):
        """Process an audio chunk."""
        self.stream.write(audio_chunk)
    
    def wait_for_recognition_done(self):
        """Wait for recognition to complete."""
        return self.recognition_done_event.wait()
    
    def close(self):
        """Clean up resources."""
        self.stream.close()


# Helper function to create a speech recognition manager
def create_speech_manager(
    message_callback=None, 
    recognition_done_event=None,
    transcription_result=None,
    output_websocket=None
):
    """
    Create and return a new speech recognition manager.
    
    Args:
        message_callback: (Legacy) Function to call with recognition messages
        recognition_done_event: Optional event to signal recognition completion
        transcription_result: Optional TranscriptionResult object to update
        output_websocket: Optional WebSocket to send transcription updates to
        
    Returns:
        SpeechRecognitionManager: Configured speech recognition manager
    """
    return SpeechRecognitionManager(
        message_callback=message_callback,
        recognition_done_event=recognition_done_event,
        transcription_result=transcription_result,
        output_websocket=output_websocket
    ) 