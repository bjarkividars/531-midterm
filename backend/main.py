from fastapi import FastAPI, WebSocket, Request, Depends, UploadFile, File, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocketState
import logging
from contextlib import asynccontextmanager
from app.services.transcription import websocket_transcribe, TranscriptionResult, send_messages, process_with_pinecone_assistant_text_only
from app.services.pinecone_assistant import PineconeAssistant
from app.services.speech_recognition import create_speech_manager
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import socket
import time
from pynput.keyboard import Key, Controller
from pynput.mouse import Button, Controller as MouseController
import subprocess
import platform
import pyautogui
import asyncio

# uvicorn main:app --reload
logger = logging.getLogger("app_logger")
logger.setLevel(logging.INFO)

# Create console handler with formatting
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

async def get_pinecone_assistant(websocket: WebSocket) -> PineconeAssistant:
    assistant = websocket.app.state.pinecone_assistant
    if assistant is None:
        raise RuntimeError("Pinecone assistant has not been initialized")
    return assistant


async def get_pinecone_assistant_http(request: Request) -> PineconeAssistant:
    """Dependency for getting the Pinecone assistant in HTTP endpoints"""
    assistant = request.app.state.pinecone_assistant
    if assistant is None:
        raise RuntimeError("Pinecone assistant has not been initialized")
    return assistant


# Define a model for presentation context
class PresentationContext(BaseModel):
    context: str

# Define a model for key command input


class KeyCommand(BaseModel):
    command: str


# Define window coordinates for the two applications
# These will need to be adjusted for your specific setup
# X, Y coordinates to click for focusing left window
LEFT_WINDOW_COORDS = (400, 400)
# X, Y coordinates to click for focusing right window
RIGHT_WINDOW_COORDS = (1200, 400)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the assistant on startup
    try:
        # Create and initialize the assistant asynchronously
        assistant = await PineconeAssistant.create(app)

        # Store the assistant instance on app.state
        app.state.pinecone_assistant = assistant

        # Initialize presentation context
        app.state.presentation_context = ""

        # Initialize current window tracking
        app.state.current_window = "left"
        
        # Initialize output websocket connection
        app.state.output_websocket = None

        logging.info("PineconeAssistant initialized successfully")

        # Uncomment to upload knowledge files during startup
        # upload_result = await assistant.upload_knowledge_files()
        # logging.info(f"Knowledge base initialized: {upload_result}")
    except Exception as e:
        logging.error(f"Error initializing PineconeAssistant: {e}")
        raise

    yield

    # Cleanup on shutdown if needed
    app.state.pinecone_assistant = None
    app.state.presentation_context = ""
    app.state.current_window = "left"
    app.state.output_websocket = None

app = FastAPI(
    title="FastAPI Project",
    description="A basic FastAPI project structure",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# Provide a route for the index


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html") as f:
        return f.read()


@app.post("/upload-knowledge-files/")
async def upload_knowledge_files(
    files: List[UploadFile] = File(...),
    pinecone_assistant: PineconeAssistant = Depends(
        get_pinecone_assistant_http)
):
    """
    Upload files to the knowledge base for embedding and vectorization.

    Files will be temporarily saved to the 'knowledge' directory and then
    processed by the PineconeVectorStore.
    """
    # Create knowledge directory if it doesn't exist
    knowledge_dir = os.path.join(os.getcwd(), "knowledge")
    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)

    saved_files = []
    try:
        # Save uploaded files to knowledge directory
        for file in files:
            file_path = os.path.join(knowledge_dir, file.filename)

            # Read file content
            content = await file.read()

            # Write to knowledge directory
            with open(file_path, "wb") as f:
                f.write(content)

            saved_files.append(file_path)

        # Process the files with the vector store
        result = await pinecone_assistant.upload_knowledge_files()

        return JSONResponse(
            content={
                "message": "Files uploaded and processed successfully",
                "files": [os.path.basename(f) for f in saved_files],
                "upload_result": result
            },
            status_code=200
        )
    except Exception as e:
        # Clean up any saved files on error
        for file_path in saved_files:
            if os.path.exists(file_path):
                os.remove(file_path)

        logging.error(f"Error processing uploaded files: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing uploaded files: {str(e)}"
        )


@app.get("/knowledge-files/")
async def get_knowledge_files():
    """
    Get a list of all knowledge files currently stored.

    Returns a JSON response with file details including name, size, and date modified.
    """
    knowledge_dir = os.path.join(os.getcwd(), "knowledge")
    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)

    files = []
    for filename in os.listdir(knowledge_dir):
        file_path = os.path.join(knowledge_dir, filename)
        if os.path.isfile(file_path):
            file_stats = os.stat(file_path)
            files.append({
                "name": filename,
                "size": file_stats.st_size,
                "modified": file_stats.st_mtime,
                "path": file_path
            })

    return JSONResponse(
        content={
            "files": files
        },
        status_code=200
    )


@app.delete("/knowledge-files/{filename}")
async def delete_knowledge_file(
    filename: str,
    pinecone_assistant: PineconeAssistant = Depends(
        get_pinecone_assistant_http)
):
    """
    Delete a specific knowledge file and its associated vector embeddings.

    Args:
        filename: Name of the file to delete

    Returns:
        JSON response indicating success or failure
    """
    knowledge_dir = os.path.join(os.getcwd(), "knowledge")
    file_path = os.path.join(knowledge_dir, filename)

    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found"
        )

    try:
        # Delete the file
        os.remove(file_path)

        # Delete associated vector embeddings from Pinecone
        # This will need to be implemented in PineconeVectorStore
        if hasattr(pinecone_assistant.vector_store, 'delete_file_vectors'):
            await pinecone_assistant.vector_store.delete_file_vectors(filename)

        return JSONResponse(
            content={
                "message": f"File '{filename}' deleted successfully",
                "deleted": True
            },
            status_code=200
        )
    except Exception as e:
        logging.error(f"Error deleting file '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting file: {str(e)}"
        )


@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket, pinecone_assistant: PineconeAssistant = Depends(get_pinecone_assistant)):
    await websocket_transcribe(websocket, pinecone_assistant)


@app.post("/presentation-context/")
async def update_presentation_context(
    context_data: PresentationContext,
    assistant: PineconeAssistant = Depends(get_pinecone_assistant_http)
) -> Dict[str, Any]:
    """Update the presentation context"""
    try:
        # Update the presentation context on the assistant
        assistant.presentation_context = context_data.context

        return {
            "status": "success",
            "message": "Presentation context updated successfully"
        }
    except Exception as e:
        logging.error(f"Error updating presentation context: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update presentation context: {str(e)}"
        )


@app.get("/presentation-context/")
async def get_presentation_context(
    assistant: PineconeAssistant = Depends(get_pinecone_assistant_http)
) -> Dict[str, Any]:
    """Get the current presentation context"""
    try:
        return {
            "status": "success",
            "context": assistant.presentation_context
        }
    except Exception as e:
        logging.error(f"Error getting presentation context: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get presentation context: {str(e)}"
        )


@app.websocket("/ws/output")
async def output_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for sending output messages (transcriptions, assistant responses)
    to the frontend. Accepts only one connection.
    """
    await websocket.accept()
    logger.info("Output WebSocket connection accepted")
    if websocket.app.state.output_websocket is not None:
        logger.warning("Output WebSocket already connected. Closing new connection.")
        await websocket.close(code=1008, reason="Already connected")
        return

    # Store in app state
    websocket.app.state.output_websocket = websocket
    
    # Send an initial connection confirmation
    try:
        await websocket.send_json({
            "type": "connection_established",
            "message": "Output WebSocket connection established"
        })
        logger.info("Sent connection confirmation to output websocket")
    except Exception as e:
        logger.error(f"Error sending connection confirmation: {e}")

    # Create a heartbeat task to keep the connection alive
    heartbeat_task = None
    
    async def send_heartbeat():
        try:
            while True:
                try:
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_json({"type": "heartbeat"})
                        logger.debug("Sent heartbeat to output websocket")
                    await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                except Exception as e:
                    logger.error(f"Error in heartbeat: {e}")
                    break
        except asyncio.CancelledError:
            # Normal cancellation when websocket closes
            pass
    
    try:
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(send_heartbeat())
        
        # Keep the connection alive, waiting for messages to be sent *to* it
        while True:
            # We don't expect messages from the client on this endpoint,
            # but we need to keep it open and check for disconnects.
            try:
                # Use a timeout to check the connection periodically
                message = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                logger.debug(f"Received unexpected message on output websocket: {message}")
            except asyncio.TimeoutError:
                # This is expected - just continue
                continue
    except WebSocketDisconnect:
        logger.info("Output WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in output WebSocket: {e}", exc_info=True)
    finally:
        # Cancel heartbeat task
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Clear from app state
        websocket.app.state.output_websocket = None
        logger.info("Output WebSocket connection closed and cleared from state")

@app.websocket("/ws/unified")
async def unified_websocket_endpoint(websocket: WebSocket, pinecone_assistant: PineconeAssistant = Depends(get_pinecone_assistant)):
    """
    Unified WebSocket endpoint that handles incoming directional commands and audio streaming.
    Output messages are sent via the separate /ws/output endpoint.

    Receives:
    - Text messages: Directional commands like "forward", "backward", "up", "down"
    - Binary data: Audio chunks for speech recognition
    - "END" text message: Signal to stop receiving audio and process the transcription
    """
    await websocket.accept()
    logger.info("Unified Input WebSocket connection accepted")

    # Initialize speech recognition components
    recognition_done = asyncio.Event()
    transcription_result = TranscriptionResult()

    # Get the output websocket if available
    output_websocket = websocket.app.state.output_websocket
    if output_websocket:
        logger.info("Output websocket is available - partial transcriptions will be sent")
    else:
        logger.warning("No output websocket connected - partial transcriptions will not be sent")

    # Create speech manager with transcription result and output websocket
    speech_manager = create_speech_manager(
        message_callback=None,
        recognition_done_event=recognition_done,
        transcription_result=transcription_result,
        output_websocket=output_websocket
    )

    is_audio_streaming = False

    try:
        while True:
            try:
                data = await websocket.receive()

                if "bytes" in data:
                    audio_chunk = data["bytes"]
                    if audio_chunk:
                        if not is_audio_streaming:
                            logger.info("Starting speech recognition on first audio chunk")
                            speech_manager.start_recognition()
                            is_audio_streaming = True
                        speech_manager.process_audio_chunk(audio_chunk)
                    else:
                        logger.info("Received empty audio chunk")

                elif "text" in data:
                    command = data["text"]

                    if command == "END":
                        if is_audio_streaming:
                            logger.info("Received END command, processing audio")
                            speech_manager.stop_recognition()
                            await recognition_done.wait()

                            complete_text = transcription_result.get_complete_text()
                            logger.info(f"Complete transcription text: {complete_text[:50]}...")

                            # Send completion message via output websocket
                            output_ws = websocket.app.state.output_websocket
                            if output_ws and complete_text:
                                 await output_ws.send_json({
                                    "type": "complete_transcription",
                                    "data": complete_text
                                })

                            # Process with Pinecone assistant if available
                            if pinecone_assistant and complete_text.strip():
                                logger.info("Processing with assistant (text only)")
                                await process_with_pinecone_assistant_text_only(
                                    complete_text,
                                    pinecone_assistant
                                )

                            # Reset audio streaming state
                            is_audio_streaming = False
                            recognition_done = asyncio.Event()
                            transcription_result = TranscriptionResult()

                            # Get current output websocket (it may have changed)
                            current_output_ws = websocket.app.state.output_websocket
                            
                            # Recreate speech manager for next audio stream
                            speech_manager.close()
                            speech_manager = create_speech_manager(
                                message_callback=None,
                                recognition_done_event=recognition_done,
                                transcription_result=transcription_result,
                                output_websocket=current_output_ws
                            )
                        else:
                             logger.info("Received END command but not streaming audio.")

                    # Directional commands
                    elif command in ['right', 'left', 'up', 'down']:
                         actual_command = {
                            'right': 'forward',
                            'left': 'backward',
                            'up': 'up',
                            'down': 'down'
                         }[command]
                         logger.info(f"Processing directional command: {command} -> {actual_command}")
                         await process_directional_command(actual_command)
                    else:
                        logger.warning(f"Received unknown command: {command}")

            except WebSocketDisconnect:
                logger.info("Unified Input WebSocket disconnected")
                break
            except Exception as e:
                logger.error(f"Error in unified input WebSocket: {e}", exc_info=True)
                # Send error via output ws
                output_ws = websocket.app.state.output_websocket
                if output_ws:
                    try:
                        await output_ws.send_json({
                            "status": "error",
                            "message": f"Server error processing input: {str(e)}"
                        })
                    except Exception as send_e:
                         logger.error(f"Failed to send error to output websocket: {send_e}")
                break

    finally:
        # Clean up resources
        if is_audio_streaming and speech_manager:
            logger.info("Cleaning up active speech recognition stream on disconnect.")
            speech_manager.stop_recognition()

        if speech_manager:
            speech_manager.close()

        logger.info("Unified Input WebSocket connection closed")

# Extract the directional command processing logic for reuse


async def process_directional_command(command: str) -> Dict[str, Any]:
    """Process directional commands (forward, backward, up, down)"""
    if command not in ["forward", "backward", "up", "down"]:
        raise ValueError(
            f"Invalid command: {command}. Accepted commands are: forward, backward, up, down.")

    try:
        if platform.system() == "Darwin":  # macOS
            # Save the current mouse position
            original_position = pyautogui.position()

            if command in ["forward", "backward"]:
                # PowerPoint control on secondary monitor
                key_to_press = "right" if command == "forward" else "left"

                # Create AppleScript to control PowerPoint
                applescript = f'''
                tell application "Figma"
                    activate
                    tell application "System Events"
                        key code {124 if command == "forward" else 123}
                    end tell
                end tell
                '''

                # Execute the AppleScript
                result = subprocess.run(["osascript", "-e", applescript],
                                        capture_output=True, text=True)

                # Return focus to the previous application (most likely Chrome)
                # Adjust the delay as needed
                time.sleep(0.2)

                # Return mouse to original position
                pyautogui.moveTo(original_position[0], original_position[1])

                return {
                    "status": "success",
                    "message": f"Successfully sent {key_to_press} arrow key to Figma",
                    "application": "Figma",
                    "command": command
                }
            else:  # "up" or "down"
                # Chrome scrolling on main monitor
                # First, make sure Chrome is active
                applescript = '''
                tell application "Google Chrome"
                    activate
                end tell
                '''
                subprocess.run(["osascript", "-e", applescript],
                               capture_output=True, text=True)

                # Now send the key
                key_to_press = Key.up if command == "up" else Key.down
                keyboard = Controller()
                keyboard.press(key_to_press)
                time.sleep(0.1  )
                keyboard.release(key_to_press)

                # Return mouse to original position
                pyautogui.moveTo(original_position[0], original_position[1])

                return {
                    "status": "success",
                    "message": f"Successfully scrolled {command} in Chrome",
                    "application": "Google Chrome",
                    "command": command
                }
        else:
            # Fallback for non-macOS systems
            keyboard = Controller()
            key_mapping = {
                "forward": Key.right,
                "backward": Key.left,
                "up": Key.up,
                "down": Key.down
            }

            key = key_mapping[command]
            keyboard.press(key)
            time.sleep(0.1)
            keyboard.release(key)

            return {
                "status": "success",
                "message": f"Successfully emulated key press: {command}",
                "key": str(key)
            }
    except Exception as e:
        logging.error(f"Error emulating key press: {e}")
        raise Exception(f"Failed to emulate key press: {str(e)}")

# Update the POST endpoint to use the same function for consistency


@app.post("/input")
async def handle_input(
    key_command: KeyCommand
) -> Dict[str, Any]:
    """
    Emulate key presses based on received command.

    Accepted commands:
    - "forward": Press right arrow key to advance PowerPoint slide on secondary monitor
    - "backward": Press left arrow key to go back in PowerPoint slides on secondary monitor
    - "up": Press up arrow key to scroll up in Chrome on main monitor
    - "down": Press down arrow key to scroll down in Chrome on main monitor

    Returns a JSON response indicating which key was pressed.
    """
    try:
        return await process_directional_command(key_command.command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    # Get the machine's IP address on the local network
    def get_local_ip():
        try:
            # Create a socket that connects to an external server to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Doesn't actually connect
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"  # Fallback to localhost if unable to determine IP

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Get local IP and port
    host = "0.0.0.0"  # Listen on all network interfaces
    port = 8000
    local_ip = get_local_ip()

    # Log the URLs where the server can be accessed
    print(f"Starting server at:")
    print(f"    Local:      http://localhost:{port}")
    print(f"    Network:    http://{local_ip}:{port}")

    # Run the server
    uvicorn.run("main:app", host=host, port=port, reload=True)
