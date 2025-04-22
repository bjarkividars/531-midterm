import { useState, useRef, useEffect, useCallback } from 'react'
import { Transcription as TranscriptionComponent } from './components/Transcription'
import { KnowledgeFileSidebar } from './components/KnowledgeFileSidebar'
import { Teleprompter } from './components/teleprompter/Teleprompter'
import styles from './App.module.css'
import { 
  WebSocketRefs,
  WebSocketHandlers,
  cleanupResources,
  connectToWebSocket,
  disconnectFromWebSocket
} from './services/WebSocketService'

export const App = () => {
  // Transcription state
  const [finalTranscription, setFinalTranscription] = useState("");
  const [partialTranscription, setPartialTranscription] = useState("");
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
    console.log(`Updating transcription: ${text} (${type})`);
    
    if (type === "partial") {
      // Replace the current partial transcription
      setPartialTranscription(text);
    } else if (type === "final") {
      // Append to final transcription and clear partial
      setFinalTranscription(prev => prev + (prev ? ' ' : '') + text);
      setPartialTranscription("");
    } else if (type === "section") {
      // Ignoring section type for now
    }
  };
  
  // For displaying status messages
  const appendMessage = (text: string, type: string) => {
    console.log(`${type}: ${text}`);
  };

  // Function to clear transcriptions
  const clearTranscription = () => {
    setFinalTranscription("");
    setPartialTranscription("");
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
    setFinalTranscription("");
    setPartialTranscription("");
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
        <h1 className={styles.logo}>Podium<span className={styles.highlight}>Pro</span></h1>
        <p className={styles.tagline}>Confidence at the Click of a Button</p>
        
        <TranscriptionComponent
          transcriptions={finalTranscription + (partialTranscription ? ' ' + partialTranscription : '')}
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

