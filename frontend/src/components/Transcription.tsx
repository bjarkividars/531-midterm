import { FC } from "react";
import styles from "./Transcription.module.css";

interface Message {
  text: string;
  type: "partial" | "final" | "section" | "status";
}

interface TranscriptionProps {
  messages: Message[];
  transcriptions: string;
  isRecording: boolean;
  onStartRecording: () => void;
  onStopRecording: (command: "STOP_DISCARD" | "STOP_PROCESS") => void;
}

export const Transcription: FC<TranscriptionProps> = ({
  messages,
  transcriptions,
  isRecording,
  onStartRecording,
  onStopRecording,
}) => {
  return (
    <div className={styles.outerContainer}>
      <div className={styles.transcriptionContainer}>
        <div className={styles.controls}>
          {!isRecording ? (
            <button className={styles.startButton} onClick={onStartRecording}>
              Start Recording
            </button>
          ) : (
            <div className={styles.recordingControls}>
              <button
                className={styles.stopButton}
                onClick={() => onStopRecording("STOP_DISCARD")}
              >
                Discard
              </button>
              <button
                className={styles.stopButton}
                onClick={() => onStopRecording("STOP_PROCESS")}
              >
                Process
              </button>
              <div className={styles.recordingIndicator}>
                <span className={styles.recordingDot}></span>
                Recording...
              </div>
            </div>
          )}
        </div>

        {/* Status messages container */}
        <div className={styles.messagesContainer}>
          {messages.map((msg, idx) => (
            <div key={idx} className={`${styles.message} ${styles[msg.type]}`}>
              {msg.text}
            </div>
          ))}
        </div>

        {/* Current transcription display */}
        {transcriptions && (
          <div className={styles.currentTranscriptionContainer}>
            <div className={`${styles.currentTranscription}`}>
              {transcriptions}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
