import azure.cognitiveservices.speech as speechsdk
import asyncio
import logging
from typing import Callable, Optional, Any
from app.config import settings

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
                 message_callback: Callable[[str], Any], 
                 recognition_done_event: Optional[asyncio.Event] = None):
        """
        Initialize the speech recognition manager.
        
        Args:
            message_callback: Callback function to receive recognition messages
            recognition_done_event: Optional event to signal when recognition is done
        """
        self.message_callback = message_callback
        self.recognition_done_event = recognition_done_event or asyncio.Event()
        audio_format = speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        self.stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
        self.audio_config = speechsdk.audio.AudioConfig(stream=self.stream)
        self.speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, 
            audio_config=self.audio_config
        )
        
        # Set up event handlers
        self.setup_event_handlers()
    
    def setup_event_handlers(self):
        """Set up the event handlers for the speech recognizer."""
        def recognizing_handler(evt):
            logger.debug(f'Recognizing: {evt.result.text}')
            self.message_callback(f"PARTIAL: {evt.result.text}")

        def recognized_handler(evt):
            logger.debug(f'Recognized: {evt.result.text}')
            self.message_callback(f"FINAL: {evt.result.text}")

        def session_stopped_handler(evt):
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
def create_speech_manager(message_callback, recognition_done_event=None):
    """
    Create and return a new speech recognition manager.
    
    Args:
        message_callback: Function to call with recognition messages
        recognition_done_event: Optional event to signal recognition completion
        
    Returns:
        SpeechRecognitionManager: Configured speech recognition manager
    """
    return SpeechRecognitionManager(
        message_callback=message_callback,
        recognition_done_event=recognition_done_event
    ) 