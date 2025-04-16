from fastapi import FastAPI, WebSocket, Request, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
from contextlib import asynccontextmanager
from app.services.transcription import websocket_transcribe
from app.services.pinecone_assistant import PineconeAssistant
import os
from typing import List, Dict, Any
from pydantic import BaseModel
import socket
import time
from pynput.keyboard import Key, Controller
from pynput.mouse import Button, Controller as MouseController
import subprocess
import platform
import pyautogui

# uvicorn main:app --reload       

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
LEFT_WINDOW_COORDS = (400, 400)  # X, Y coordinates to click for focusing left window
RIGHT_WINDOW_COORDS = (1200, 400)  # X, Y coordinates to click for focusing right window

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the assistant on startup
    try:
        # Create and initialize the assistant asynchronously
        assistant = await PineconeAssistant.create()
        
        # Store the assistant instance on app.state
        app.state.pinecone_assistant = assistant
        
        # Initialize presentation context
        app.state.presentation_context = ""
        
        # Initialize current window tracking
        app.state.current_window = "left"
        
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
    pinecone_assistant: PineconeAssistant = Depends(get_pinecone_assistant_http)
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
    pinecone_assistant: PineconeAssistant = Depends(get_pinecone_assistant_http)
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
    if key_command.command not in ["forward", "backward", "up", "down"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid command: {key_command.command}. Accepted commands are: forward, backward, up, down."
        )
    
    try:
        if platform.system() == "Darwin":  # macOS
            # Save the current mouse position
            original_position = pyautogui.position()
            
            if key_command.command in ["forward", "backward"]:
                # PowerPoint control on secondary monitor
                key_to_press = "right" if key_command.command == "forward" else "left"
                
                # Create AppleScript to control PowerPoint
                applescript = f'''
                tell application "Microsoft PowerPoint"
                    activate
                    tell application "System Events"
                        key code {124 if key_command.command == "forward" else 123}
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
                    "message": f"Successfully sent {key_to_press} arrow key to PowerPoint",
                    "application": "Microsoft PowerPoint",
                    "command": key_command.command
                }
            else:  # "up" or "down"
                # Chrome scrolling on main monitor
                # First, make sure Chrome is active
                applescript = '''
                tell application "Google Chrome"
                    activate
                end tell
                '''
                subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
                
                # Now send the key
                key_to_press = Key.up if key_command.command == "up" else Key.down
                keyboard = Controller()
                keyboard.press(key_to_press)
                time.sleep(0.1)
                keyboard.release(key_to_press)
                
                # Return mouse to original position
                pyautogui.moveTo(original_position[0], original_position[1])
                
                return {
                    "status": "success",
                    "message": f"Successfully scrolled {key_command.command} in Chrome",
                    "application": "Google Chrome",
                    "command": key_command.command
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
            
            key = key_mapping[key_command.command]
            keyboard.press(key)
            time.sleep(0.1)
            keyboard.release(key)
            
            return {
                "status": "success",
                "message": f"Successfully emulated key press: {key_command.command}",
                "key": str(key)
            }
    except Exception as e:
        logging.error(f"Error emulating key press: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to emulate key press: {str(e)}"
        )

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