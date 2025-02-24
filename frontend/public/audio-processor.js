class AudioProcessor extends AudioWorkletProcessor {
    process(inputs, outputs, parameters) {
      // Use the first channel of the first input.
      const input = inputs[0];
      if (input && input[0]) {
        const channelData = input[0];
        // Create an ArrayBuffer to hold 16-bit PCM data.
        const buffer = new ArrayBuffer(channelData.length * 2);
        const dataView = new DataView(buffer);
        
        // Convert each sample from Float32 to 16-bit PCM.
        for (let i = 0; i < channelData.length; i++) {
          let sample = channelData[i];
          sample = Math.max(-1, Math.min(1, sample));
          dataView.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
        }
        
        // Send the converted data to the main thread.
        this.port.postMessage(buffer);
      }
      // Keep the processor alive.
      return true;
    }
  }
  
  registerProcessor('audio-processor', AudioProcessor);