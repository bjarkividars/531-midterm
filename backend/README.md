# PodiumPro Backend

This backend application powers the PodiumPro presentation system, processing audio inputs from the Raspberry Pi client, managing the knowledge base, and generating AI-powered responses.

## Features

- Real-time audio transcription (speech-to-text)
- Knowledge base management with Pinecone vector database
- Retrieval-Augmented Generation (RAG) for informed responses
- Text-to-speech conversion for audio responses
- WebSocket communication with Raspberry Pi client
- Direct system automation for presentation control
- FastAPI-based REST API for managing knowledge files
- Presentation slide navigation control
- Response scrolling control via joystick input

## Technologies Used

- Python 3.9+
- FastAPI
- Pinecone (vector database)
- WebSockets
- Azure Cognitive Services Speech SDK
- OpenAI/GPT integration
- PyAutoGUI for system automation
- AppleScript (on macOS) for application control
- pynput for keyboard control

## Prerequisites

- Python 3.9 or higher
- Virtual environment (recommended)
- Azure Cognitive Services account for speech services
- Pinecone account for vector database
- OpenAI API key

## Getting Started

1. **Set up a virtual environment**

```bash
cd backend
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

Create a `.env` file in the backend directory with the following variables:

```
OPENAI_API_KEY=your_openai_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=your_pinecone_environment
PINECONE_INDEX_NAME=your_index_name
AZURE_SPEECH_KEY=your_azure_speech_key
AZURE_SPEECH_REGION=your_azure_region
```

4. **Start the server**

```bash
uvicorn main:app --reload
```

The server will start at http://localhost:8000.

## API Endpoints

- `GET /` - Root endpoint, serves the main HTML page
- `POST /upload-knowledge-files/` - Upload files to the knowledge base
- `GET /knowledge-files/` - List all files in the knowledge base
- `DELETE /knowledge-files/{filename}` - Delete a file from the knowledge base
- `WebSocket /ws/unified` - WebSocket endpoint for Raspberry Pi client (joystick navigation and audio streaming)

## Project Structure

- `app/` - Application modules
  - `services/` - Service modules for transcription, RAG, etc.
- `knowledge/` - Storage for knowledge base files
- `static/` - Static files
- `main.py` - FastAPI application entry point
- `requirements.txt` - Python dependencies

## Knowledge Base Management

You can upload PDF files and other documents to build your knowledge base. These files are processed and stored in Pinecone's vector database for efficient retrieval during question answering.

## Direct System Control

The PodiumPro backend directly controls your computer based on inputs from the Raspberry Pi:

### Slide Navigation
- The Raspberry Pi client sends joystick directional input (left/right) via the unified WebSocket
- Backend interprets these commands as slide navigation instructions:
  - Left/Right: Navigate to previous/next slide
- The backend uses PyAutoGUI and AppleScript (on macOS) to directly control presentation software:
  - Activates Figma (or your presentation application)
  - Programmatically sends keyboard events (left/right arrow keys)
  - Returns focus to the original application when done

### Response Scrolling
- When AI-generated responses are longer than the display area, the Raspberry Pi joystick can control scrolling
- Vertical joystick movements (up/down) are interpreted as scroll commands
- The backend uses direct system automation to control scrolling:
  - Activates Google Chrome (or your browser)
  - Sends keyboard events (up/down arrow keys) to control scrolling
  - Returns focus to the original application when done
- This allows the presenter to control the visible portion of content without touching the computer

## How It Works

![System Architecture Diagram](images/system-diagram.png)

The system operates through the following steps:

1. The Raspberry Pi client captures joystick movement for slide navigation and response scrolling
2. Audience questions are recorded via the Raspberry Pi and sent to the backend
3. The backend transcribes the audio using Azure's speech services
4. The transcribed question is used to query the Pinecone vector database
5. Relevant information is retrieved from the knowledge base
6. The question and retrieved context are sent to GPT to generate an answer
7. The answer is streamed to the frontend

## Troubleshooting

- If you encounter WebSocket connection issues, ensure you don't have firewall restrictions
- For Azure speech service errors, verify your API keys and region settings
- If Pinecone isn't responding, check your API key and index configuration
- Memory issues might occur with large knowledge bases - consider adjusting chunk sizes
- For joystick control problems, check the Raspberry Pi client connection status
- If system control isn't working, ensure your backend has the correct permissions to control applications