import { useRef, useCallback } from 'react';
import styles from './Teleprompter.module.css';

interface TeleprompterProps {
  text: string;
  onClose: () => void;
}

export const Teleprompter = ({ 
  text, 
  onClose
}: TeleprompterProps) => {
  const textContainerRef = useRef<HTMLDivElement>(null);
  
  // Handle closing the teleprompter
  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);
  
  return (
    <div className={styles.teleprompterContainer}>
      <div className={styles.teleprompterBackdrop} onClick={handleClose}></div>
      <div className={styles.teleprompterContent}>
        <button className={styles.closeButton} onClick={handleClose}>×</button>
        <h3>Assistant Response</h3>
        <div className={styles.scrollContainer}>
          <div ref={textContainerRef} className={styles.teleprompterText}>
            {text}
          </div>
        </div>
      </div>
    </div>
  );
}; 