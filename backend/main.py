from fastapi import FastAPI, WebSocket, Request, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
from contextlib import asynccontextmanager
from app.services.transcription import websocket_transcribe
from app.services.pinecone_assistant import PineconeAssistant
import os
from typing import List

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the assistant on startup
    try:
        # Create and initialize the assistant asynchronously
        assistant = await PineconeAssistant.create()
        
        # Store the assistant instance on app.state
        app.state.pinecone_assistant = assistant
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

if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("main:app", host="localhost", port=8000, reload=True) 