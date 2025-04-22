import { MutableRefObject } from 'react';

// Message types
export interface Message {
  text: string;
  type: "status" | "partial" | "final" | "section";
}

export interface Transcription {
  text: string;
  type: "partial" | "final" | "section";
}

export interface WebSocketRefs {
  outputWs: MutableRefObject<WebSocket | null>;
}

export interface WebSocketHandlers {
  appendMessage: (text: string, type: string) => void;
  updateTranscription: (text: string, type: "partial" | "final" | "section") => void;
  setAssistantResponse: (response: string | ((prev: string) => string)) => void;
  setIsShowingResponse: (isShowing: boolean) => void;
  setIsLoading: (isLoading: boolean) => void;
  setIsConnected: (isConnected: boolean) => void;
  clearTranscription: () => void;
}

/**
 * Clean up WebSocket resources
 */
export const cleanupResources = (refs: WebSocketRefs): void => {
  // Clean up output WebSocket
  if (refs.outputWs.current) {
    refs.outputWs.current.onclose = null;
    refs.outputWs.current.close();
    refs.outputWs.current = null;
  }
};

/**
 * Initialize the output WebSocket
 */
export const initOutputWebSocket = async (
  refs: WebSocketRefs,
  handlers: WebSocketHandlers
): Promise<void> => {
  const wsUrl = `ws://localhost:8000/ws/output`;
  
  try {
    refs.outputWs.current = new WebSocket(wsUrl);
    
    refs.outputWs.current.onopen = () => {
      handlers.appendMessage("Connected to output websocket", "status");
      handlers.setIsConnected(true);
    };
    
    refs.outputWs.current.onmessage = (event: MessageEvent) => {
      try {
        const jsonData = JSON.parse(event.data);
        
        // Handle different message types based on the example
        switch(jsonData.type) {
          case "connection_established":
            handlers.appendMessage(jsonData.message, "status");
            break;
            
          case "heartbeat":
            // Ignore heartbeat messages
            break;
            
          case "partial_transcription":
            // Close teleprompter if it's open when new transcription comes in
            handlers.setIsShowingResponse(false);
            handlers.updateTranscription(jsonData.text, "partial");
            break;
            
          case "final_transcription_segment":
            handlers.updateTranscription(jsonData.text, "final");
            break;
            
          case "complete_transcription":
            handlers.updateTranscription(jsonData.data, "section");
            handlers.setIsLoading(true);
            break;
            
          case "processing_start":
            handlers.appendMessage(jsonData.message, "status");
            // Clear previous transcription when assistant starts responding
           
            handlers.setAssistantResponse("");
            handlers.setIsShowingResponse(true);
            break;
            
          case "text_delta":
            handlers.clearTranscription();
            handlers.setAssistantResponse((prev) => prev + jsonData.text);
            handlers.setIsLoading(false);
            break;
            
          case "text_complete":
            handlers.appendMessage("Assistant's response complete", "status");
            break;
            
          case "error":
            handlers.appendMessage(`Error: ${jsonData.message}`, "status");
            handlers.setIsLoading(false);
            break;
            
          default:
            console.log("Unknown message type:", jsonData.type);
        }
      } catch (e) {
        console.error("Error parsing message as JSON:", e);
        handlers.appendMessage(`Error parsing message: ${e}`, "status");
      }
    };
    
    refs.outputWs.current.onerror = () => {
      handlers.appendMessage("WebSocket error occurred", "status");
      handlers.setIsLoading(false);
      handlers.setIsConnected(false);
    };
    
    refs.outputWs.current.onclose = () => {
      handlers.appendMessage("WebSocket connection closed", "status");
      handlers.setIsLoading(false);
      handlers.setIsConnected(false);
    };
  } catch (err) {
    handlers.appendMessage(`Error creating WebSocket connection: ${err}`, "status");
    handlers.setIsLoading(false);
    handlers.setIsConnected(false);
  }
};

/**
 * Connect to output websocket
 */
export const connectToWebSocket = async (
  refs: WebSocketRefs,
  handlers: WebSocketHandlers,
  resetState: () => void
): Promise<void> => {
  resetState();
  
  console.log("Connecting to output websocket...");
  
  // Clean up any existing connection
  cleanupResources(refs);
  
  // Initialize output WebSocket
  await initOutputWebSocket(refs, handlers);
};

/**
 * Disconnect from output websocket
 */
export const disconnectFromWebSocket = (
  refs: WebSocketRefs,
  handlers: WebSocketHandlers
): void => {
  if (!refs.outputWs.current) return;
  
  console.log("Disconnecting from output websocket");
  
  // Close the WebSocket connection
  if (refs.outputWs.current.readyState === WebSocket.OPEN) {
    refs.outputWs.current.close();
  }
  
  handlers.setIsConnected(false);
  handlers.appendMessage("Disconnected from output websocket", "status");
}; 