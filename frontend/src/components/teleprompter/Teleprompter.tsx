import { useRef, useCallback, useEffect } from 'react';
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
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  
  // Handle closing the teleprompter
  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);
  
  // Handle keyboard events for scrolling
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (!scrollContainerRef.current) return;
    
    const scrollAmount = 50; // Adjust scroll amount as needed
    
    switch (event.key) {
      case 'ArrowUp':
        event.preventDefault();
        scrollContainerRef.current.scrollTop -= scrollAmount;
        break;
      case 'ArrowDown':
        event.preventDefault();
        scrollContainerRef.current.scrollTop += scrollAmount;
        break;
    }
  }, []);
  
  // Add and remove event listeners
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    
    // Focus the container to ensure it captures keyboard events
    if (scrollContainerRef.current) {
      scrollContainerRef.current.focus();
    }
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);
  
  return (
    <div className={styles.teleprompterContainer}>
      <div className={styles.teleprompterBackdrop} onClick={handleClose}></div>
      <div className={styles.teleprompterContent}>
        <button className={styles.closeButton} onClick={handleClose}>×</button>
        <h3>Assistant Response</h3>
        <div 
          ref={scrollContainerRef} 
          className={styles.scrollContainer} 
          tabIndex={0} // Make it focusable
        >
          <div ref={textContainerRef} className={styles.teleprompterText}>
            {text}
          </div>
        </div>
      </div>
    </div>
  );
}; 