import { FC } from "react";
import styles from "./Transcription.module.css";

interface TranscriptionProps {
  transcriptions: string;
  isConnected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}

export const Transcription: FC<TranscriptionProps> = ({
  transcriptions,
  isConnected,
  onConnect,
  onDisconnect,
}) => {
  return (
    <div className={styles.outerContainer}>
      <div className={styles.transcriptionContainer}>
        <div className={styles.controls}>
          {!isConnected ? (
            <button className={styles.startButton} onClick={onConnect}>
              Connect
            </button>
          ) : (
            <div className={styles.recordingControls}>
              <button
                className={styles.stopButton}
                onClick={onDisconnect}
              >
                Disconnect
              </button>
              <div className={styles.recordingIndicator}>
                <span className={styles.recordingDot}></span>
                Connected
              </div>
            </div>
          )}
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
