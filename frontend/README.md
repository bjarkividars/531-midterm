# Live Question-Answering Assistant Frontend

This frontend application provides a user interface for the Live Question-Answering Assistant system. It allows users to record audio questions, send them to the backend for processing, and receive responses.

## Features

- Real-time audio recording and streaming
- WebSocket communication with the backend
- Knowledge base management interface
- Modern React + TypeScript implementation

## Technologies Used

- React 19
- TypeScript
- Vite
- WebSockets for real-time communication
- CSS Modules for styling

## Prerequisites

- Node.js (v18+)
- npm or yarn

## Getting Started

1. **Install dependencies**

```bash
cd frontend
npm install
# or
yarn install
```

2. **Set up environment**

Make sure the backend server is running (see backend README).

3. **Start the development server**

```bash
npm run dev
# or
yarn dev
```

This will start the Vite development server, typically on http://localhost:5173.

4. **Build for production**

```bash
npm run build
# or
yarn build
```

The build output will be in the `dist` directory.

## Project Structure

- `src/` - Source code
  - `components/` - React components
  - `services/` - API and WebSocket services
  - `assets/` - Static assets
  - `App.tsx` - Main application component
  - `main.tsx` - Application entry point

## Usage

1. Open the application in your browser
2. Ensure your microphone is enabled
3. Click the record button to start capturing audio
4. The application will stream your audio to the backend
5. The backend will process your question and stream the response back to the frontend

## Troubleshooting

- If you encounter WebSocket connection issues, make sure the backend server is running
- For microphone access problems, check that your browser has permission to use the microphone
- If audio recording doesn't work, try using a different browser (Chrome is recommended)