import { useState, useRef, useCallback } from 'react';
import styles from './FileUpload.module.css';

export const FileUpload = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ success: boolean; message: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const openModal = () => {
    setIsModalOpen(true);
    setUploadStatus(null);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedFiles([]);
    setUploadStatus(null);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      const filesArray = Array.from(event.target.files);
      setSelectedFiles(filesArray);
      setUploadStatus(null);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer.files) {
      const filesArray = Array.from(event.dataTransfer.files);
      setSelectedFiles(filesArray);
      setUploadStatus(null);
    }
  };

  const uploadFiles = useCallback(async () => {
    if (selectedFiles.length === 0) return;

    setIsUploading(true);
    setUploadStatus(null);

    try {
      const formData = new FormData();
      selectedFiles.forEach(file => {
        formData.append('files', file);
      });

      const response = await fetch('http://127.0.0.1:8000/upload-knowledge-files/', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        setUploadStatus({
          success: true,
          message: `Files uploaded successfully! ${data.files.length} file(s) added to the knowledge base.`,
        });
        // Clear the file selection after successful upload
        setSelectedFiles([]);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      } else {
        setUploadStatus({
          success: false,
          message: data.detail || 'Upload failed. Please try again.',
        });
      }
    } catch (error) {
      console.error('Upload error:', error);
      setUploadStatus({
        success: false,
        message: 'Upload failed. Please try again.',
      });
    } finally {
      setIsUploading(false);
    }
  }, [selectedFiles]);

  return (
    <div className={styles.fileUploadContainer}>
      <button 
        className={styles.uploadButton}
        onClick={openModal}
      >
        Upload Knowledge Files
      </button>

      {isModalOpen && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h2>Upload Files to Knowledge Base</h2>
            <p>Upload text files to be processed and added to the knowledge base for future queries.</p>
            
            <div 
              className={styles.dropZone} 
              onDragOver={handleDragOver} 
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input 
                type="file" 
                ref={fileInputRef}
                onChange={handleFileChange} 
                multiple 
                style={{ display: 'none' }}
              />
              <div className={styles.dropZoneContent}>
                <p>Drop files here or click to select</p>
                {selectedFiles.length > 0 && (
                  <div className={styles.selectedFiles}>
                    <p>Selected files:</p>
                    <ul>
                      {selectedFiles.map((file, index) => (
                        <li key={index}>{file.name}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>

            {uploadStatus && (
              <div className={`${styles.statusMessage} ${uploadStatus.success ? styles.success : styles.error}`}>
                {uploadStatus.message}
              </div>
            )}

            <div className={styles.actionButtons}>
              <button 
                className={styles.cancelButton} 
                onClick={closeModal}
                disabled={isUploading}
              >
                Close
              </button>
              <button 
                className={styles.submitButton} 
                onClick={uploadFiles}
                disabled={selectedFiles.length === 0 || isUploading}
              >
                {isUploading ? 'Uploading...' : 'Upload Files'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}; 