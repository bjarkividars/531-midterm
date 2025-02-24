import { useEffect, useRef, useState, useCallback } from 'react';
import styles from './Transcription.module.css';

interface Message {
  text: string;
  type: 'partial' | 'final' | 'section' | 'status';
}

export const Transcription = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement>(new Audio());
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const audioBlobsRef = useRef<Blob[]>([]);
  const isPlayingResponseRef = useRef(false);

  const appendMessage = (text: string, type: Message['type']) => {
    setMessages((prev: Message[]) => [...prev, { text, type }]);
  };

  const playNextAudioChunk = useCallback(async () => {
    if (audioQueueRef.current.length > 0 && !isPlayingResponseRef.current) {
      isPlayingResponseRef.current = true;
      
      const chunks = [];
      while (audioQueueRef.current.length > 0) {
        chunks.push(audioQueueRef.current.shift()!);
      }
      
      const blob = new Blob(chunks, { type: 'audio/mp3' });
      audioBlobsRef.current.push(blob);
      
      const audioUrl = URL.createObjectURL(blob);
      audioPlayerRef.current.src = audioUrl;
      
      try {
        console.log('Starting audio playback...');
        await audioPlayerRef.current.play();
        appendMessage("Playing assistant's response...", 'status');
      } catch (error) {
        console.error('Error playing audio:', error);
        isPlayingResponseRef.current = false;
        URL.revokeObjectURL(audioUrl);
      }
    }
  }, []);

  const stopRecording = (command: 'STOP_DISCARD' | 'STOP_PROCESS') => {
    if (sourceRef.current) {
      sourceRef.current.disconnect();
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
    }
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track: MediaStreamTrack) => track.stop());
    }
    
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(command);
    }
    
    setIsRecording(false);
    appendMessage(`Recording stopped with ${command}`, 'status');
  };

  const startRecording = async () => {
    setMessages([]);
    audioQueueRef.current = [];
      audioBlobsRef.current = [];
      
    console.log('Starting recording...');
    
    if (!navigator.mediaDevices) {
      appendMessage("mediaDevices is not available in this browser/context", 'status');
      return;
    }
      
    console.log('Navigator media devices available');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//127.0.0.1:8000/ws/transcribe`;
    console.log('WebSocket URL:', wsUrl);
    wsRef.current = new WebSocket(wsUrl);
    wsRef.current.binaryType = "arraybuffer";

    wsRef.current.onopen = async () => {
      setIsConnected(true);
      appendMessage("WebSocket connected.", 'status');
      try {
        audioStreamRef.current = await navigator.mediaDevices.getUserMedia({ 
          audio: { sampleRate: 16000, channelCount: 1 } 
        });
        
        // Create the AudioContext.
        audioContextRef.current = new AudioContext({ sampleRate: 16000 });
        
        // Load the AudioWorklet module.
        await audioContextRef.current.audioWorklet.addModule('/audio-processor.js');
        
        // Create a MediaStreamAudioSourceNode from the stream.
        sourceRef.current = audioContextRef.current.createMediaStreamSource(audioStreamRef.current);
        
        // Create the AudioWorkletNode that uses our custom processor.
        const workletNode = new AudioWorkletNode(audioContextRef.current, 'audio-processor');
        
        // Listen for processed audio data from the worklet.
        workletNode.port.onmessage = (event: MessageEvent) => {
          // Send the audio data via WebSocket.
          wsRef.current?.send(event.data);
        };
        
        // Connect the source to the worklet.
        sourceRef.current.connect(workletNode);
        // Optionally, if you want to monitor the audio:
        // workletNode.connect(audioContextRef.current.destination);

        setIsRecording(true);
        appendMessage("Recording started.", 'status');
      } catch (err) {
        appendMessage(`Error accessing microphone: ${err}`, 'status');
      }
    };

    wsRef.current.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        console.log('Received audio chunk:', event.data.byteLength, 'bytes');
        audioQueueRef.current.push(event.data);
        playNextAudioChunk();
      } else {
        const message = event.data as string;
        if (message.startsWith("PARTIAL: ")) {
          appendMessage(message.substring(9), 'partial');
        } else if (message.startsWith("FINAL: ")) {
          appendMessage(message.substring(7), 'final');
        } else if (message.startsWith("COMPLETE_TRANSCRIPTION: ")) {
          appendMessage(message.substring(23), 'section');
        } else if (message === "RESPONSE_COMPLETE") {
          appendMessage("Assistant's response complete", 'status');
        } else {
          appendMessage(message, 'status');
        }
      }
    };

    wsRef.current.onerror = () => {
      appendMessage("WebSocket error occurred.", 'status');
    };

    wsRef.current.onclose = () => {
      setIsConnected(false);
      setIsRecording(false);
      appendMessage("WebSocket connection closed.", 'status');
    };
  };

  useEffect(() => {
    const audioPlayer = audioPlayerRef.current;
    
    const handleAudioEnded = () => {
      console.log('Audio chunk finished playing');
      URL.revokeObjectURL(audioPlayer.src);
      isPlayingResponseRef.current = false;
      
      if (audioQueueRef.current.length > 0) {
        playNextAudioChunk();
      } else if (audioBlobsRef.current.length > 0) {
        const finalBlob = new Blob(audioBlobsRef.current, { type: 'audio/mp3' });
        console.log('Created final audio blob:', finalBlob.size, 'bytes');
        audioBlobsRef.current = [];
      }
    };

    audioPlayer.addEventListener('ended', handleAudioEnded);
    
    return () => {
      audioPlayer.removeEventListener('ended', handleAudioEnded);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [playNextAudioChunk]);

  return (
    <div className={styles.transcriptionContainer}>
      <h1>WebSocket Transcription</h1>
      <div className={styles.buttonContainer}>
        <button 
          onClick={startRecording}
          disabled={isRecording}
        >
          Start Recording
        </button>
        <button 
          onClick={() => stopRecording('STOP_DISCARD')}
          disabled={!isRecording}
        >
          Stop & Discard
        </button>
        <button 
          onClick={() => stopRecording('STOP_PROCESS')}
          disabled={!isRecording}
        >
          Stop & Process
        </button>
      </div>
      <div className={styles.output}>
        {messages.map((message, index) => (
          <div 
            key={index} 
            className={`${styles.message} ${message.type}`}
          >
            {message.type === 'section' ? (
              <>
                <div className={styles.sectionHeader}>Transcription Result:</div>
                <div>{message.text}</div>
              </>
            ) : (
              message.text
            )}
          </div>
        ))}
      </div>
    </div>
  );
};