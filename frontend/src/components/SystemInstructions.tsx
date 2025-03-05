import { useState, useEffect } from "react";
import styles from "./SystemInstructions.module.css";

export const SystemInstructions = () => {
  const [presentationContext, setPresentationContext] = useState("");
  const [originalContext, setOriginalContext] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isChanged, setIsChanged] = useState(false);

  // Fetch current presentation context from the backend
  const fetchPresentationContext = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/presentation-context/"
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Error: ${response.status}`);
      }

      const data = await response.json();
      if (data.context) {
        setPresentationContext(data.context);
        setOriginalContext(data.context);
      } else {
        setPresentationContext("");
        setOriginalContext("");
      }
      setIsChanged(false);
    } catch (err) {
      console.error("Error fetching presentation context:", err);
      setPresentationContext("");
      setOriginalContext("");
    } finally {
      setIsLoading(false);
    }
  };

  // Save presentation context to the backend
  const savePresentationContext = async () => {
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/presentation-context/",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ context: presentationContext }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Error: ${response.status}`);
      }

      // We don't need the response data anymore
      await response.json();
      setSuccessMessage("Presentation context updated successfully!");
      setOriginalContext(presentationContext);
      setIsChanged(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
      console.error("Error saving presentation context:", err);
    } finally {
      setIsSaving(false);
    }
  };

  // Handle text changes
  const handleContextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setPresentationContext(newValue);
    setIsChanged(newValue !== originalContext);
  };

  // Cancel changes
  const cancelChanges = () => {
    setPresentationContext(originalContext);
    setIsChanged(false);
    setError(null);
    setSuccessMessage(null);
  };

  // Fetch context on component mount
  useEffect(() => {
    fetchPresentationContext();
  }, []);

  if (isLoading) {
    return (
      <div className={styles.instructionsContainer}>
        <div className={styles.loadingMessage}>
          Loading presentation context...
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className={styles.instructionsHeader}>
        <h3>Presentation Context</h3>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {successMessage && <div className={styles.success}>{successMessage}</div>}

      <div className={styles.contextHelp}>
        Add details about your presentation topic to help the assistant
        provide more relevant answers.
      </div>
      <textarea
        className={styles.instructionsEditor}
        value={presentationContext}
        onChange={handleContextChange}
        placeholder="E.g., This presentation is about climate change mitigation strategies in urban environments, focusing on renewable energy adoption and sustainable transportation."
        disabled={isSaving}
        rows={6}
      />
       {isChanged && (
          <div className={styles.editControls}>
            <button
              className={styles.cancelButton}
              onClick={cancelChanges}
              disabled={isSaving}
            >
              Cancel
            </button>
            <button
              className={styles.saveButton}
              onClick={savePresentationContext}
              disabled={isSaving}
            >
              {isSaving ? "Saving..." : "Save"}
            </button>
          </div>
        )}
    </div>
  );
};
