from fastapi import FastAPI, WebSocket, Request, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
from contextlib import asynccontextmanager
from app.services.assistant import KnowledgeAssistant
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

@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket, pinecone_assistant: PineconeAssistant = Depends(get_pinecone_assistant)):
    await websocket_transcribe(websocket, pinecone_assistant)

if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("main:app", host="localhost", port=8000, reload=True) 