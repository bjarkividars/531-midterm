/**
 * Audio Handler for ordered sentence playback
 * 
 * This class handles the ordered playback of audio sentences
 * received from the WebSocket connection.
 */
class OrderedAudioHandler {
    constructor() {
        this.sentences = new Map(); // Map of sentence ID to audio chunks
        this.currentSentenceId = 0; // Current sentence being played
        this.nextSentenceToPlay = 1; // Next sentence ID to play
        this.isPlaying = false;
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.audioQueue = [];
        this.onSentenceStart = null; // Callback for when a sentence starts playing
        this.onSentenceEnd = null; // Callback for when a sentence ends playing
        this.onAllAudioComplete = null; // Callback for when all audio is complete
    }

    /**
     * Handle a message from the WebSocket
     * @param {Object|Blob} message - The message from the WebSocket
     */
    handleMessage(message) {
        console.log("Received message type:", typeof message, 
                    message instanceof Blob ? "Blob" : 
                    message instanceof ArrayBuffer ? "ArrayBuffer" : "Other");
        
        // Check if this is a JSON message (sentence markers)
        if (typeof message === 'string' || message instanceof String) {
            console.log("Handling text message:", message.substring(0, 100) + (message.length > 100 ? "..." : ""));
            try {
                const data = JSON.parse(message);
                console.log("Successfully parsed JSON message:", data);
                this.handleJsonMessage(data);
            } catch (e) {
                console.error('Error parsing JSON message:', e, "Original message:", message);
            }
            return;
        }
        
        // Handle if message is already JSON object
        if (message !== null && typeof message === 'object' && !(message instanceof Blob) && !(message instanceof ArrayBuffer)) {
            console.log("Handling object message:", message);
            this.handleJsonMessage(message);
            return;
        }

        // Handle binary message (audio chunk)
        if (message instanceof Blob) {
            console.log(`Received binary blob of size ${message.size} bytes`);
            // Convert blob to array buffer
            message.arrayBuffer().then(buffer => {
                console.log(`Converted blob to ArrayBuffer of size ${buffer.byteLength} bytes`);
                // If we're currently collecting chunks for a sentence, add this chunk
                if (this.currentSentenceId > 0) {
                    if (!this.sentences.has(this.currentSentenceId)) {
                        console.log(`Creating new array for sentence ${this.currentSentenceId}`);
                        this.sentences.set(this.currentSentenceId, []);
                    }
                    this.sentences.get(this.currentSentenceId).push(buffer);
                    console.log(`Added chunk to sentence ${this.currentSentenceId}, now has ${this.sentences.get(this.currentSentenceId).length} chunks`);
                } else {
                    console.warn("Received audio chunk but no current sentence ID is set");
                }
            });
        } else if (message instanceof ArrayBuffer) {
            console.log(`Received ArrayBuffer of size ${message.byteLength} bytes`);
            // If we're currently collecting chunks for a sentence, add this chunk
            if (this.currentSentenceId > 0) {
                if (!this.sentences.has(this.currentSentenceId)) {
                    console.log(`Creating new array for sentence ${this.currentSentenceId}`);
                    this.sentences.set(this.currentSentenceId, []);
                }
                this.sentences.get(this.currentSentenceId).push(message);
                console.log(`Added chunk to sentence ${this.currentSentenceId}, now has ${this.sentences.get(this.currentSentenceId).length} chunks`);
            } else {
                console.warn("Received audio chunk but no current sentence ID is set");
            }
        } else {
            console.error("Unhandled message type:", message);
        }
    }

    /**
     * Handle a JSON message from the WebSocket
     * @param {Object} data - The parsed JSON message
     */
    handleJsonMessage(data) {
        switch (data.type) {
            case 'sentence_start':
                console.log(`Starting to collect chunks for sentence ${data.id}: ${data.text}`);
                this.currentSentenceId = data.id;
                this.sentences.set(this.currentSentenceId, []);
                break;

            case 'sentence_end':
                console.log(`Finished collecting chunks for sentence ${data.id}`);
                // Check if we should start playing
                this.checkAndPlayNext();
                break;

            case 'audio_complete':
                console.log('All audio has been received');
                this.checkAndPlayNext();
                break;
        }
    }

    /**
     * Check if we should play the next sentence and play it if ready
     */
    checkAndPlayNext() {
        // If we're already playing, the next sentence will be played automatically
        if (this.isPlaying) return;

        // Check if the next sentence to play is available
        if (this.sentences.has(this.nextSentenceToPlay)) {
            this.playNextSentence();
        }
    }

    /**
     * Play the next sentence in the queue
     */
    async playNextSentence() {
        if (!this.sentences.has(this.nextSentenceToPlay)) {
            // No more sentences to play
            this.isPlaying = false;
            if (this.onAllAudioComplete) {
                this.onAllAudioComplete();
            }
            return;
        }

        this.isPlaying = true;
        const sentenceId = this.nextSentenceToPlay;
        const chunks = this.sentences.get(sentenceId);
        
        // Notify that we're starting a new sentence
        if (this.onSentenceStart) {
            this.onSentenceStart(sentenceId);
        }

        console.log(`Playing sentence ${sentenceId} (${chunks.length} chunks)`);

        // Concatenate all chunks into a single buffer
        const totalLength = chunks.reduce((acc, chunk) => acc + chunk.byteLength, 0);
        const audioData = new Uint8Array(totalLength);
        let offset = 0;
        
        for (const chunk of chunks) {
            audioData.set(new Uint8Array(chunk), offset);
            offset += chunk.byteLength;
        }

        // Decode the audio data
        try {
            const audioBuffer = await this.audioContext.decodeAudioData(audioData.buffer);
            
            // Create a source node
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            
            // When this sentence finishes playing, play the next one
            source.onended = () => {
                console.log(`Finished playing sentence ${sentenceId}`);
                if (this.onSentenceEnd) {
                    this.onSentenceEnd(sentenceId);
                }
                this.nextSentenceToPlay++;
                this.playNextSentence();
            };
            
            // Start playing
            source.start();
        } catch (e) {
            console.error('Error decoding audio data:', e);
            // Move on to the next sentence
            this.nextSentenceToPlay++;
            this.playNextSentence();
        }
    }

    /**
     * Reset the audio handler
     */
    reset() {
        this.sentences.clear();
        this.currentSentenceId = 0;
        this.nextSentenceToPlay = 1;
        this.isPlaying = false;
    }
}

// Example usage:
/*
const audioHandler = new OrderedAudioHandler();

// Set up callbacks
audioHandler.onSentenceStart = (sentenceId) => {
    console.log(`Started playing sentence ${sentenceId}`);
};

audioHandler.onSentenceEnd = (sentenceId) => {
    console.log(`Finished playing sentence ${sentenceId}`);
};

audioHandler.onAllAudioComplete = () => {
    console.log('All audio playback complete');
};

// In your WebSocket message handler:
socket.onmessage = (event) => {
    if (event.data instanceof Blob) {
        // Binary message (audio chunk)
        audioHandler.handleMessage(event.data);
    } else {
        // Text message (could be JSON)
        try {
            const data = JSON.parse(event.data);
            audioHandler.handleMessage(data);
        } catch (e) {
            // Handle other text messages
            console.log('Received text message:', event.data);
        }
    }
};
*/ 