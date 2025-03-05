import { useState, useRef, useEffect, useCallback } from 'react'
import { Transcription as TranscriptionComponent } from './components/Transcription'
import { KnowledgeFileSidebar } from './components/KnowledgeFileSidebar'
import { Teleprompter } from './components/teleprompter/Teleprompter'
import styles from './App.module.css'
import { 
  Message, 
  Transcription, 
  WebSocketRefs,
  WebSocketHandlers,
  cleanupResources,
  startRecording as wsStartRecording,
  stopRecording as wsStopRecording
} from './services/WebSocketService'

export const App = () => {
  // Transcription state
  const [messages, setMessages] = useState<Message[]>([]);
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  
  // Teleprompter state
  const [assistantResponse, setAssistantResponse] = useState("");
  const [isShowingResponse, setIsShowingResponse] = useState(false);
  
  // Loading state for waiting on assistant response
  const [isLoading, setIsLoading] = useState(false);
  
  // WebSocket and audio refs
  const transcriptionWsRef = useRef<WebSocket | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  // WebSocket refs object
  const refs: WebSocketRefs = {
    transcriptionWs: transcriptionWsRef,
    audioStream: audioStreamRef,
    audioContext: audioContextRef,
    audioSource: sourceRef
  };

  // Helper for appending messages
  const appendMessage = (text: string, type: Message["type"]) => {
    if (type === "status") {
      setMessages((prev) => [...prev, { text, type }]);
    } else if (type === "partial" || type === "final") {
      setTranscriptions((prev) => {
        const newTranscriptions = [...prev];
        // If the last message was partial, replace it with the new message
        // (whether partial or final)
        if (newTranscriptions.length > 0 && 
            newTranscriptions[newTranscriptions.length - 1].type === "partial") {
          newTranscriptions[newTranscriptions.length - 1] = { text, type };
        } else {
          // Otherwise add a new message
          newTranscriptions.push({ text, type });
        }
        return newTranscriptions;
      });
    }
  };

  // WebSocket handlers object
  const handlers: WebSocketHandlers = {
    appendMessage,
    setIsRecording,
    setAssistantResponse,
    setIsShowingResponse,
    setIsLoading
  };

  // Reset state function for startRecording
  const resetState = useCallback(() => {
    setMessages([]);
    setTranscriptions([]);
    setAssistantResponse("");
    setIsShowingResponse(false);
    setIsLoading(false);
  }, []);

  // Start recording wrapper function
  const startRecording = useCallback(async () => {
    await wsStartRecording(refs, handlers, resetState);
  }, [resetState]);

  // Stop recording wrapper function
  const stopRecording = useCallback((command: "STOP_DISCARD" | "STOP_PROCESS") => {
    wsStopRecording(refs, handlers, isRecording, command);
  }, [isRecording]);

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
          messages={messages}
          transcriptions={transcriptions.map((t) => t.text).join(" ")}
          isRecording={isRecording}
          onStartRecording={startRecording}
          onStopRecording={stopRecording}
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

