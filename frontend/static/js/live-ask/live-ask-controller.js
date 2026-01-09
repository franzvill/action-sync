/**
 * LiveAskController - Push-to-Talk Voice Questions
 *
 * Hold mic button to record, release to transcribe and ask.
 */

import { AudioCaptureManager } from '/static/js/live-ask/audio-capture.js';
import { WhisperTranscriber } from '/static/js/live-ask/whisper-transcriber.js';

export class LiveAskController {
    constructor(options = {}) {
        // Components
        this.audioCapture = new AudioCaptureManager({
            onAudioCaptured: (audio, sampleRate) => this.handleAudioCaptured(audio, sampleRate),
            onError: (err) => this.handleError(err),
            onStatusChange: (status) => this.updateStatus(status),
        });

        this.transcriber = new WhisperTranscriber({
            onLoadProgress: (progress) => this.handleModelProgress(progress),
            onError: (err) => this.handleError(err),
        });

        // State
        this.ready = false;
        this.status = 'idle'; // 'idle' | 'loading' | 'recording' | 'transcribing' | 'processing'
        this.modelProgress = 0;

        // Callbacks
        this.onStatusChange = options.onStatusChange || (() => {});
        this.onModelProgress = options.onModelProgress || (() => {});
        this.onTranscription = options.onTranscription || (() => {});
        this.onError = options.onError || console.error;

        // Question handler (will be set to call askQuestion)
        this.askQuestionHandler = options.askQuestionHandler || null;
    }

    /**
     * Check if Live Ask is supported in this browser
     */
    static isSupported() {
        return AudioCaptureManager.isSupported();
    }

    /**
     * Get detailed support info
     */
    static getSupportInfo() {
        return AudioCaptureManager.getSupportInfo();
    }

    /**
     * Initialize - load Whisper model
     */
    async initialize() {
        if (this.ready) return;

        try {
            this.updateStatus('loading');

            // Load Whisper model (can take time on first load)
            if (!this.transcriber.isLoaded) {
                console.log('[LiveAsk] Loading Whisper model...');
                await this.transcriber.loadModel();
                console.log('[LiveAsk] Whisper model loaded');
            }

            // Request mic permission early
            await this.audioCapture.requestMicrophoneAccess();

            this.ready = true;
            this.updateStatus('idle');

        } catch (error) {
            console.error('[LiveAsk] Initialize error:', error);
            this.updateStatus('idle');
            this.handleError(error);
            throw error;
        }
    }

    /**
     * Start recording (call on button press)
     */
    async startRecording() {
        if (!this.ready) {
            await this.initialize();
        }

        try {
            await this.audioCapture.startRecording();
            this.updateStatus('recording');
        } catch (error) {
            this.handleError(error);
        }
    }

    /**
     * Stop recording and process (call on button release)
     */
    async stopRecording() {
        this.audioCapture.stopRecording();
        // Audio will be processed via onAudioCaptured callback
    }

    /**
     * Handle captured audio
     */
    async handleAudioCaptured(audioData, sampleRate) {
        console.log(`[LiveAsk] Audio captured: ${audioData.length} samples`);

        try {
            this.updateStatus('transcribing');

            // Transcribe the audio
            const text = await this.transcriber.transcribe(audioData);
            console.log('[LiveAsk] Transcription:', text);

            if (!text || text.trim().length < 3) {
                console.log('[LiveAsk] Transcription too short, ignoring');
                this.updateStatus('idle');
                return;
            }

            this.onTranscription(text.trim());

            // Process as question (no intent detection needed - user intentionally recorded)
            if (this.askQuestionHandler) {
                this.updateStatus('processing');
                await this.askQuestionHandler(text.trim());
            }

            this.updateStatus('idle');

        } catch (error) {
            this.handleError(error);
            this.updateStatus('idle');
        }
    }

    /**
     * Handle model loading progress
     */
    handleModelProgress(progress) {
        this.modelProgress = progress.progress;
        this.onModelProgress(progress);
    }

    /**
     * Update status and notify
     */
    updateStatus(status) {
        this.status = status;
        this.onStatusChange(status);
    }

    /**
     * Handle errors
     */
    handleError(error) {
        console.error('[LiveAsk] Error:', error);
        this.onError(error);
    }

    /**
     * Set the question handler
     */
    setAskQuestionHandler(handler) {
        this.askQuestionHandler = handler;
    }

    /**
     * Get current state
     */
    getState() {
        return {
            ready: this.ready,
            status: this.status,
            modelLoaded: this.transcriber.isLoaded,
            modelLoading: this.transcriber.isLoading,
            modelProgress: this.modelProgress,
            isRecording: this.audioCapture.getIsRecording(),
        };
    }

    /**
     * Cleanup resources
     */
    destroy() {
        this.audioCapture.cleanup();
        this.transcriber.unloadModel();
        this.ready = false;
    }
}

// Export singleton instance
let instance = null;

export function getLiveAskController(options) {
    if (!instance) {
        instance = new LiveAskController(options);
    }
    return instance;
}

export function destroyLiveAskController() {
    if (instance) {
        instance.destroy();
        instance = null;
    }
}
