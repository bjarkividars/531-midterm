import { MutableRefObject } from 'react';

// Message types
export interface Message {
  text: string;
  type: "partial" | "final" | "section" | "status";
}

export interface Transcription {
  text: string;
  type: "partial" | "final" | "section";
}

export interface WebSocketRefs {
  transcriptionWs: MutableRefObject<WebSocket | null>;
  audioStream: MutableRefObject<MediaStream | null>;
  audioContext: MutableRefObject<AudioContext | null>;
  audioSource: MutableRefObject<MediaStreamAudioSourceNode | null>;
}

export interface WebSocketHandlers {
  appendMessage: (text: string, type: Message["type"]) => void;
  setIsRecording: (isRecording: boolean) => void;
  setAssistantResponse: (response: string | ((prev: string) => string)) => void;
  setIsShowingResponse: (isShowing: boolean) => void;
  setIsLoading: (isLoading: boolean) => void;
}

/**
 * Clean up all WebSocket and audio resources
 */
export const cleanupResources = (refs: WebSocketRefs): void => {
  // Clean up transcription WebSocket
  if (refs.transcriptionWs.current) {
    refs.transcriptionWs.current.onclose = null;
    refs.transcriptionWs.current.close();
    refs.transcriptionWs.current = null;
  }
  
  // Clean up audio resources
  if (refs.audioSource.current) {
    refs.audioSource.current.disconnect();
    refs.audioSource.current = null;
  }
  
  if (refs.audioStream.current) {
    refs.audioStream.current.getTracks().forEach(track => track.stop());
    refs.audioStream.current = null;
  }
  
  if (refs.audioContext.current) {
    refs.audioContext.current.close();
    refs.audioContext.current = null;
  }
};

/**
 * Initialize the transcription WebSocket
 */
export const initTranscriptionWebSocket = async (
  refs: WebSocketRefs,
  handlers: WebSocketHandlers
): Promise<void> => {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//127.0.0.1:8000/ws/transcribe`;
  
  try {
    refs.transcriptionWs.current = new WebSocket(wsUrl);
    refs.transcriptionWs.current.binaryType = "arraybuffer";
    
    refs.transcriptionWs.current.onopen = async () => {
      handlers.appendMessage("Connection established. You can start speaking.", "status");
      
      try {
        // Request microphone access
        refs.audioStream.current = await navigator.mediaDevices.getUserMedia({
          audio: { sampleRate: 16000, channelCount: 1 },
        });
        
        // Create the AudioContext
        refs.audioContext.current = new AudioContext({ sampleRate: 16000 });
        
        // Load the AudioWorklet module
        await refs.audioContext.current.audioWorklet.addModule("/audio-processor.js");
        
        // Create a MediaStreamAudioSourceNode from the stream
        refs.audioSource.current = refs.audioContext.current.createMediaStreamSource(
          refs.audioStream.current
        );
        
        // Create the AudioWorkletNode that uses our custom processor
        const workletNode = new AudioWorkletNode(
          refs.audioContext.current,
          "audio-processor"
        );
        
        // Listen for processed audio data from the worklet
        workletNode.port.onmessage = (event: MessageEvent) => {
          // Send the audio data via WebSocket if connection is open
          if (
            refs.transcriptionWs.current?.readyState === WebSocket.OPEN
          ) {
            refs.transcriptionWs.current.send(event.data);
          }
        };
        
        // Connect the source to the worklet
        refs.audioSource.current.connect(workletNode);
        
        handlers.setIsRecording(true);
        handlers.appendMessage("Recording started.", "status");
      } catch (err) {
        handlers.appendMessage(`Error accessing microphone: ${err}`, "status");
      }
    };
    
    refs.transcriptionWs.current.onmessage = (event: MessageEvent) => {
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
          handlers.appendMessage(jsonData.message, "status");
          // Reset the assistant response when a new processing starts
          handlers.setAssistantResponse("");
          handlers.setIsShowingResponse(true);
          // Stop loading when processing starts and response begins
          handlers.setIsLoading(false);
        } else if (jsonData.type === "text_delta") {
          // Append to the assistant response for teleprompter display
          handlers.setAssistantResponse((prev) => prev + jsonData.text);
        } else if (jsonData.type === "text_complete") {
          handlers.appendMessage("Assistant's response complete", "status");
        } else if (jsonData.type === "error") {
          handlers.appendMessage(`Error: ${jsonData.message}`, "status");
          // Clear loading state on error
          handlers.setIsLoading(false);
        }
        
        return;
      } catch (e) {
        // Not JSON, handle as regular text
        console.error("Error parsing message as JSON:", e);
        
        if (message.startsWith("PARTIAL: ")) {
          handlers.appendMessage(message.substring(9), "partial");
        } else if (message.startsWith("FINAL: ")) {
          handlers.appendMessage(message.substring(7), "final");
        } else if (message.startsWith("COMPLETE_TRANSCRIPTION: ")) {
          handlers.appendMessage(message.substring(23), "section");
        } else {
          handlers.appendMessage(message, "status");
        }
      }
    };
    
    refs.transcriptionWs.current.onerror = () => {
      handlers.appendMessage("WebSocket error occurred.", "status");
      handlers.setIsLoading(false); // Clear loading state on error
    };
    
    refs.transcriptionWs.current.onclose = () => {
      handlers.setIsRecording(false);
      handlers.appendMessage("WebSocket connection closed.", "status");
      handlers.setIsLoading(false); // Clear loading state on close
    };
  } catch (err) {
    handlers.appendMessage(`Error creating WebSocket connection: ${err}`, "status");
    handlers.setIsLoading(false); // Clear loading state on error
  }
};

/**
 * Start recording audio
 */
export const startRecording = async (
  refs: WebSocketRefs,
  handlers: WebSocketHandlers,
  resetState: () => void
): Promise<void> => {
  resetState();
  
  console.log("Starting recording...");
  
  if (!navigator.mediaDevices) {
    handlers.appendMessage(
      "mediaDevices is not available in this browser/context",
      "status"
    );
    return;
  }
  
  // Clean up any existing resources
  cleanupResources(refs);
  
  // Initialize transcription WebSocket
  await initTranscriptionWebSocket(refs, handlers);
};

/**
 * Stop recording audio
 */
export const stopRecording = (
  refs: WebSocketRefs,
  handlers: WebSocketHandlers,
  isRecording: boolean,
  command: "STOP_DISCARD" | "STOP_PROCESS"
): void => {
  if (!refs.transcriptionWs.current || !isRecording) return;
  
  console.log(`Stopping recording with command: ${command}`);
  
  // If we're processing, set loading state to true
  if (command === "STOP_PROCESS") {
    handlers.setIsLoading(true);
  }
  
  // Stop audio tracks
  if (refs.audioStream.current) {
    refs.audioStream.current.getTracks().forEach((track) => track.stop());
  }
  
  // Disconnect audio source
  if (refs.audioSource.current) {
    refs.audioSource.current.disconnect();
  }
  
  // Close audio context
  if (refs.audioContext.current) {
    refs.audioContext.current.close();
  }
  
  // Send command to server if WebSocket is open
  if (refs.transcriptionWs.current.readyState === WebSocket.OPEN) {
    try {
      refs.transcriptionWs.current.send(command);
      handlers.appendMessage(
        `Recording stopped. ${
          command === "STOP_PROCESS"
            ? "Processing transcription..."
            : "Discarded."
        }`,
        "status"
      );
    } catch (e) {
      console.error("Error sending stop command:", e);
      handlers.setIsLoading(false); // Clear loading state on error
    }
  }
  
  handlers.setIsRecording(false);
}; 