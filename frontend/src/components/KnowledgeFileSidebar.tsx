import { useState, useEffect } from 'react';
import styles from './KnowledgeFileSidebar.module.css';
import { FileUpload } from './FileUpload';

interface KnowledgeFile {
  name: string;
  size: number;
  modified: number;
  path: string;
}

export const KnowledgeFileSidebar = () => {
  const [files, setFiles] = useState<KnowledgeFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileToDelete, setFileToDelete] = useState<KnowledgeFile | null>(null);

  // Format file size for display
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' bytes';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  // Format date for display
  const formatDate = (timestamp: number): string => {
    return new Date(timestamp * 1000).toLocaleString();
  };

  // Fetch knowledge files
  const fetchFiles = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch('http://127.0.0.1:8000/knowledge-files/');
      if (!response.ok) {
        throw new Error(`Error: ${response.status}`);
      }
      const data = await response.json();
      setFiles(data.files || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Error fetching files:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Delete a knowledge file
  const deleteFile = async (filename: string) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/knowledge-files/${filename}`, {
        method: 'DELETE',
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Error: ${response.status}`);
      }
      
      // Refresh the file list
      fetchFiles();
      
      // Close the confirmation dialog
      setFileToDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Error deleting file:', err);
    }
  };

  // Load files when component mounts
  useEffect(() => {
    fetchFiles();
  }, []);

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <h2>Knowledge Files</h2>
        {/* <button onClick={fetchFiles} className={styles.refreshButton}>
          Refresh
        </button> */}
      </div>

      <div className={styles.fileUploadContainer}>
        <FileUpload onUploadSuccess={fetchFiles} />
      </div>
      
      {isLoading && <div className={styles.loading}>Loading files...</div>}
      
      {error && <div className={styles.error}>{error}</div>}
      
      {!isLoading && files.length === 0 && !error && (
        <div className={styles.empty}>No files in the knowledge base</div>
      )}
      
      <ul className={styles.fileList}>
        {files.map((file) => (
          <li key={file.name} className={styles.fileItem}>
            <div className={styles.fileInfo}>
              <div className={styles.fileName}>{file.name}</div>
              <div className={styles.fileDetails}>
                <span>{formatFileSize(file.size)}</span>
                <span>{formatDate(file.modified)}</span>
              </div>
            </div>
            <button 
              className={styles.deleteButton}
              onClick={() => setFileToDelete(file)}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
      
      {fileToDelete && (
        <div className={styles.confirmationOverlay}>
          <div className={styles.confirmationDialog}>
            <h3>Confirm Deletion</h3>
            <p>
              Are you sure you want to delete <strong>{fileToDelete.name}</strong>?
              This action cannot be undone.
            </p>
            <div className={styles.confirmationButtons}>
              <button 
                className={styles.cancelButton}
                onClick={() => setFileToDelete(null)}
              >
                Cancel
              </button>
              <button 
                className={styles.confirmButton}
                onClick={() => deleteFile(fileToDelete.name)}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}; 