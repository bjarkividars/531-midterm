import { useState, useRef, useEffect, useCallback } from 'react'
import { Transcription as TranscriptionComponent } from './components/Transcription'
import { KnowledgeFileSidebar } from './components/KnowledgeFileSidebar'
import { Teleprompter } from './components/teleprompter/Teleprompter'
import styles from './App.module.css'
import { 
  Transcription, 
  WebSocketRefs,
  WebSocketHandlers,
  cleanupResources,
  connectToWebSocket,
  disconnectFromWebSocket
} from './services/WebSocketService'

export const App = () => {
  // Transcription state
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  
  // Teleprompter state
  const [assistantResponse, setAssistantResponse] = useState("");
  const [isShowingResponse, setIsShowingResponse] = useState(false);
  
  // Loading state for waiting on assistant response
  const [isLoading, setIsLoading] = useState(false);
  
  // WebSocket ref
  const outputWsRef = useRef<WebSocket | null>(null);

  // WebSocket refs object
  const refs: WebSocketRefs = {
    outputWs: outputWsRef
  };

  // Helper for updating transcriptions
  const updateTranscription = (text: string, type: "partial" | "final" | "section") => {
    if (type === "partial") {
      setTranscriptions((prev) => {
        const newTranscriptions = [...prev];
        // If the last message was partial, replace it with the new partial message
        if (newTranscriptions.length > 0 && 
            newTranscriptions[newTranscriptions.length - 1].type === "partial") {
          newTranscriptions[newTranscriptions.length - 1] = { text, type };
        } else {
          // Otherwise add a new partial message
          newTranscriptions.push({ text, type });
        }
        return newTranscriptions;
      });
    } else if (type === "final") {
      setTranscriptions((prev) => {
        const newTranscriptions = [...prev];
        // If the last message was partial, replace it with the final message
        if (newTranscriptions.length > 0 && 
            newTranscriptions[newTranscriptions.length - 1].type === "partial") {
          newTranscriptions[newTranscriptions.length - 1] = { text, type };
        } else {
          // Otherwise add a new final message
          newTranscriptions.push({ text, type });
        }
        return newTranscriptions;
      });
    } else if (type === "section") {
      // For complete transcriptions, just set it directly
      setTranscriptions([{ text, type: "section" }]);
    }
  };
  
  // For displaying status messages
  const appendMessage = (text: string, type: string) => {
    console.log(`${type}: ${text}`);
  };

  // Function to clear transcriptions
  const clearTranscription = () => {
    setTranscriptions([]);
  };

  // WebSocket handlers object
  const handlers: WebSocketHandlers = {
    appendMessage,
    updateTranscription,
    setAssistantResponse,
    setIsShowingResponse,
    setIsLoading,
    setIsConnected,
    clearTranscription
  };

  // Reset state function for connecting
  const resetState = useCallback(() => {
    setTranscriptions([]);
    setAssistantResponse("");
    setIsShowingResponse(false);
    setIsLoading(false);
  }, []);

  // Connect to websocket
  const connect = useCallback(async () => {
    await connectToWebSocket(refs, handlers, resetState);
  }, [resetState]);

  // Disconnect from websocket
  const disconnect = useCallback(() => {
    disconnectFromWebSocket(refs, handlers);
  }, []);

  // Handle teleprompter close
  const handleCloseTeleprompter = useCallback(() => {
    setIsShowingResponse(false);
  }, []);

  // Clean up on unmount
  useEffect(() => {
    return () => cleanupResources(refs);
  }, []);

  // Loading spinner component
  const LoadingSpinner = () => (
    <div className={styles.loadingContainer}>
      <div className={styles.loadingSpinner}></div>
      <p>Processing your question...</p>
    </div>
  );

  return (
    <div className={styles.appContainer}>
      <div className={styles.sidebarContainer}>
        <KnowledgeFileSidebar />
      </div>
      <div className={styles.mainContent}>
        <h1>PodiumPro</h1>        
        <TranscriptionComponent
          transcriptions={transcriptions.map((t) => t.text).join(" ")}
          isConnected={isConnected}
          onConnect={connect}
          onDisconnect={disconnect}
        />
        
        {isLoading && <LoadingSpinner />}
        
        {isShowingResponse && assistantResponse && (
          <Teleprompter
            text={assistantResponse}
            onClose={handleCloseTeleprompter}
          />
        )}
      </div>
    </div>
  );
};

