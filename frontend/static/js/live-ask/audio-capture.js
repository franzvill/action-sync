/**
 * AudioCaptureManager - Handles microphone capture (Push-to-Talk)
 *
 * Simple approach: hold button to record, release to transcribe.
 */

export class AudioCaptureManager {
    constructor(options = {}) {
        // Configuration
        this.sampleRate = options.sampleRate || 16000; // Whisper needs 16kHz

        // State
        this.isRecording = false;
        this.stream = null;
        this.audioContext = null;
        this.processor = null;
        this.source = null;
        this.audioBuffer = [];

        // Callbacks
        this.onAudioCaptured = options.onAudioCaptured || (() => {});
        this.onError = options.onError || console.error;
        this.onStatusChange = options.onStatusChange || (() => {});
    }

    /**
     * Check if browser supports audio capture
     */
    static isSupported() {
        return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    }

    /**
     * Get detailed support info for debugging
     */
    static getSupportInfo() {
        const isSecureContext = window.isSecureContext;
        const hasMediaDevices = !!navigator.mediaDevices;
        const hasGetUserMedia = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

        return {
            isSecureContext,
            hasMediaDevices,
            hasGetUserMedia,
            isSupported: hasGetUserMedia,
            reason: !isSecureContext
                ? 'Not a secure context (requires HTTPS or localhost)'
                : !hasMediaDevices
                    ? 'navigator.mediaDevices not available'
                    : !hasGetUserMedia
                        ? 'getUserMedia not available'
                        : 'Supported'
        };
    }

    /**
     * Request microphone permission and get stream
     */
    async requestMicrophoneAccess() {
        if (!AudioCaptureManager.isSupported()) {
            throw new Error('Audio capture not supported in this browser');
        }

        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: this.sampleRate,
                    echoCancellation: true,
                    noiseSuppression: true,
                }
            });
            console.log('[AudioCapture] Microphone access granted');
            return true;
        } catch (error) {
            if (error.name === 'NotAllowedError') {
                throw new Error('Microphone permission denied');
            }
            throw error;
        }
    }

    /**
     * Start recording audio (call on button press)
     */
    async startRecording() {
        if (this.isRecording) return;

        // Get mic access if not already done
        if (!this.stream) {
            await this.requestMicrophoneAccess();
        }

        // Create audio context
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: this.sampleRate
        });

        // Create source from stream
        this.source = this.audioContext.createMediaStreamSource(this.stream);

        // Create script processor for audio data capture
        const bufferSize = 4096;
        this.processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

        // Connect nodes
        this.source.connect(this.processor);
        this.processor.connect(this.audioContext.destination);

        // Clear buffer
        this.audioBuffer = [];

        // Process audio
        this.processor.onaudioprocess = (event) => {
            if (!this.isRecording) return;
            const inputData = event.inputBuffer.getChannelData(0);
            this.audioBuffer.push(new Float32Array(inputData));
        };

        this.isRecording = true;
        this.onStatusChange('recording');
        console.log('[AudioCapture] Recording started');
    }

    /**
     * Stop recording and return captured audio (call on button release)
     */
    stopRecording() {
        if (!this.isRecording) return null;

        this.isRecording = false;

        // Disconnect processor
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }

        if (this.source) {
            this.source.disconnect();
            this.source = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        // Concatenate all captured audio
        const audioData = this.concatenateBuffers(this.audioBuffer);
        const duration = audioData.length / this.sampleRate;
        console.log(`[AudioCapture] Recording stopped: ${duration.toFixed(2)}s, ${audioData.length} samples`);

        this.audioBuffer = [];
        this.onStatusChange('idle');

        // Return captured audio if long enough (at least 0.5s)
        if (duration >= 0.5) {
            this.onAudioCaptured(audioData, this.sampleRate);
            return audioData;
        } else {
            console.log('[AudioCapture] Recording too short, discarding');
            return null;
        }
    }

    /**
     * Concatenate Float32Array buffers into single array
     */
    concatenateBuffers(buffers) {
        const totalLength = buffers.reduce((sum, buf) => sum + buf.length, 0);
        const result = new Float32Array(totalLength);
        let offset = 0;
        for (const buffer of buffers) {
            result.set(buffer, offset);
            offset += buffer.length;
        }
        return result;
    }

    /**
     * Cleanup resources
     */
    cleanup() {
        this.stopRecording();

        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
    }

    /**
     * Check if currently recording
     */
    getIsRecording() {
        return this.isRecording;
    }
}
