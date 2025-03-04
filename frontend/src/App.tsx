import { useState, useRef, useEffect, useCallback } from 'react'
import { Transcription } from './components/Transcription'
import { KnowledgeFileSidebar } from './components/KnowledgeFileSidebar'
import { Teleprompter } from './components/teleprompter/Teleprompter'
import styles from './App.module.css'

// Message type definition
interface Message {
  text: string;
  type: "partial" | "final" | "section" | "status";
}

interface Transcription {
  text: string;
  type: "partial" | "final" | "section";
}

export const App = () => {
  // Transcription state
  const [messages, setMessages] = useState<Message[]>([]);
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  
  // Teleprompter state
  const [assistantResponse, setAssistantResponse] = useState("");
  const [isShowingResponse, setIsShowingResponse] = useState(false);
  
  // WebSocket ref
  const transcriptionWsRef = useRef<WebSocket | null>(null);
  
  // Audio refs
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

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

  // Clean up all WebSocket and audio resources
  const cleanupResources = useCallback(() => {
    // Clean up transcription WebSocket
    if (transcriptionWsRef.current) {
      transcriptionWsRef.current.onclose = null;
      transcriptionWsRef.current.close();
      transcriptionWsRef.current = null;
    }
    
    // Clean up audio resources
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach(track => track.stop());
      audioStreamRef.current = null;
    }
    
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  }, []);

  // Initialize the transcription WebSocket
  const initTranscriptionWebSocket = useCallback(async () => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//127.0.0.1:8000/ws/transcribe`;
    
    try {
      transcriptionWsRef.current = new WebSocket(wsUrl);
      transcriptionWsRef.current.binaryType = "arraybuffer";
      
      transcriptionWsRef.current.onopen = async () => {
        appendMessage("Connection established. You can start speaking.", "status");
        
        try {
          // Request microphone access
          audioStreamRef.current = await navigator.mediaDevices.getUserMedia({
            audio: { sampleRate: 16000, channelCount: 1 },
          });
          
          // Create the AudioContext
          audioContextRef.current = new AudioContext({ sampleRate: 16000 });
          
          // Load the AudioWorklet module
          await audioContextRef.current.audioWorklet.addModule("/audio-processor.js");
          
          // Create a MediaStreamAudioSourceNode from the stream
          sourceRef.current = audioContextRef.current.createMediaStreamSource(
            audioStreamRef.current
          );
          
          // Create the AudioWorkletNode that uses our custom processor
          const workletNode = new AudioWorkletNode(
            audioContextRef.current,
            "audio-processor"
          );
          
          // Listen for processed audio data from the worklet
          workletNode.port.onmessage = (event: MessageEvent) => {
            // Send the audio data via WebSocket if connection is open
            if (
              transcriptionWsRef.current?.readyState === WebSocket.OPEN
            ) {
              transcriptionWsRef.current.send(event.data);
            }
          };
          
          // Connect the source to the worklet
          sourceRef.current.connect(workletNode);
          
          setIsRecording(true);
          appendMessage("Recording started.", "status");
        } catch (err) {
          appendMessage(`Error accessing microphone: ${err}`, "status");
        }
      };
      
      transcriptionWsRef.current.onmessage = (event: MessageEvent) => {
        // Ignore binary data
        if (event.data instanceof ArrayBuffer) {
          return;
        }
        
        // Handle text messages
        const message = event.data as string;
        
        // Try to parse as JSON first
        try {
          const jsonData = JSON.parse(message);
          
          // Handle different message types
          if (jsonData.type === "processing_start") {
            appendMessage(jsonData.message, "status");
            // Reset the assistant response when a new processing starts
            setAssistantResponse("");
            setIsShowingResponse(true);
          } else if (jsonData.type === "text_delta") {
            // Append to the assistant response for teleprompter display
            setAssistantResponse((prev) => prev + jsonData.text);
          } else if (jsonData.type === "text_complete") {
            appendMessage("Assistant's response complete", "status");
          } else if (jsonData.type === "error") {
            appendMessage(`Error: ${jsonData.message}`, "status");
          }
          
          return;
        } catch (e) {
          // Not JSON, handle as regular text
          console.error("Error parsing message as JSON:", e);
          
          if (message.startsWith("PARTIAL: ")) {
            appendMessage(message.substring(9), "partial");
          } else if (message.startsWith("FINAL: ")) {
            appendMessage(message.substring(7), "final");
          } else if (message.startsWith("COMPLETE_TRANSCRIPTION: ")) {
            appendMessage(message.substring(23), "section");
          } else {
            appendMessage(message, "status");
          }
        }
      };
      
      transcriptionWsRef.current.onerror = () => {
        appendMessage("WebSocket error occurred.", "status");
      };
      
      transcriptionWsRef.current.onclose = () => {
        setIsRecording(false);
        appendMessage("WebSocket connection closed.", "status");
      };
    } catch (err) {
      appendMessage(`Error creating WebSocket connection: ${err}`, "status");
    }
  }, []);

  // Start recording
  const startRecording = useCallback(async () => {
    setMessages([]);
    setTranscriptions([]);
    setAssistantResponse("");
    setIsShowingResponse(false);
    
    console.log("Starting recording...");
    
    if (!navigator.mediaDevices) {
      appendMessage(
        "mediaDevices is not available in this browser/context",
        "status"
      );
      return;
    }
    
    // Clean up any existing resources
    cleanupResources();
    
    // Initialize transcription WebSocket
    await initTranscriptionWebSocket();
  }, [cleanupResources, initTranscriptionWebSocket]);

  // Stop recording
  const stopRecording = useCallback((command: "STOP_DISCARD" | "STOP_PROCESS") => {
    if (!transcriptionWsRef.current || !isRecording) return;
    
    console.log(`Stopping recording with command: ${command}`);
    
    // Stop audio tracks
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop());
    }
    
    // Disconnect audio source
    if (sourceRef.current) {
      sourceRef.current.disconnect();
    }
    
    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close();
    }
    
    // Send command to server if WebSocket is open
    if (transcriptionWsRef.current.readyState === WebSocket.OPEN) {
      try {
        transcriptionWsRef.current.send(command);
        appendMessage(
          `Recording stopped. ${
            command === "STOP_PROCESS"
              ? "Processing transcription..."
              : "Discarded."
          }`,
          "status"
        );
      } catch (e) {
        console.error("Error sending stop command:", e);
      }
    }
    
    setIsRecording(false);
  }, [isRecording]);

  // Handle teleprompter close
  const handleCloseTeleprompter = useCallback(() => {
    setIsShowingResponse(false);
  }, []);

  // Clean up on unmount
  useEffect(() => {
    return cleanupResources;
  }, [cleanupResources]);

  return (
    <div className={styles.appContainer}>
      <div className={styles.sidebarContainer}>
        <KnowledgeFileSidebar />
      </div>
      <div className={styles.mainContent}>
        <h1>AI Speech Assistant</h1>        
        <Transcription
          messages={messages}
          transcriptions={transcriptions.map((t) => t.text).join(" ")}
          isRecording={isRecording}
          onStartRecording={startRecording}
          onStopRecording={stopRecording}
        />
        
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

