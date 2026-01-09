/**
 * WhisperTranscriber - Local speech-to-text using Whisper via transformers.js
 *
 * Uses Hugging Face's transformers.js to run Whisper entirely in the browser.
 * Model is downloaded once and cached in IndexedDB.
 */

// We'll dynamically import transformers.js to avoid blocking page load
let pipeline = null;

export class WhisperTranscriber {
    constructor(options = {}) {
        // Model configuration - Xenova models are optimized for browser use
        this.modelId = options.modelId || 'Xenova/whisper-tiny.en';
        this.device = options.device || 'webgpu'; // 'webgpu' or 'wasm'

        // State
        this.transcriber = null;
        this.isLoading = false;
        this.isLoaded = false;

        // Callbacks
        this.onLoadProgress = options.onLoadProgress || (() => {});
        this.onError = options.onError || console.error;
    }

    /**
     * Check if WebGPU is available for faster inference
     */
    static async isWebGPUAvailable() {
        if (!navigator.gpu) return false;
        try {
            const adapter = await navigator.gpu.requestAdapter();
            return !!adapter;
        } catch {
            return false;
        }
    }

    /**
     * Load the Whisper model
     */
    async loadModel() {
        if (this.isLoaded) return;
        if (this.isLoading) {
            // Wait for existing load to complete
            while (this.isLoading) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            return;
        }

        this.isLoading = true;

        try {
            // Dynamically import transformers.js
            if (!pipeline) {
                console.log('Importing transformers.js...');
                const transformers = await import(
                    'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.0.0'
                );
                pipeline = transformers.pipeline;
                console.log('transformers.js imported successfully');
            }

            // Progress callback for model loading
            const progressCallback = (progress) => {
                console.log('Model load progress:', progress);
                if (progress.status === 'progress') {
                    const percent = Math.round((progress.loaded / progress.total) * 100);
                    this.onLoadProgress({
                        status: 'downloading',
                        progress: percent,
                        file: progress.file
                    });
                } else if (progress.status === 'ready') {
                    this.onLoadProgress({
                        status: 'ready',
                        progress: 100
                    });
                }
            };

            // Try WebGPU first, fall back to WASM with different dtypes
            const backends = [];
            const useWebGPU = await WhisperTranscriber.isWebGPUAvailable();
            if (useWebGPU) {
                backends.push({ device: 'webgpu', dtype: 'fp32' });
            }
            // WASM fallback - try without dtype first (let transformers.js choose)
            backends.push({ device: 'wasm', dtype: null });
            backends.push({ device: 'wasm', dtype: 'fp32' });

            let lastError = null;
            for (const backend of backends) {
                try {
                    console.log(`Trying ${backend.device} backend with dtype=${backend.dtype || 'auto'}...`);

                    const pipelineOptions = {
                        device: backend.device,
                        progress_callback: progressCallback
                    };

                    // Only set dtype if explicitly specified
                    if (backend.dtype) {
                        pipelineOptions.dtype = backend.dtype;
                    }

                    this.transcriber = await pipeline(
                        'automatic-speech-recognition',
                        this.modelId,
                        pipelineOptions
                    );

                    this.isLoaded = true;
                    console.log(`Whisper model loaded successfully with ${backend.device} backend`);
                    return; // Success, exit

                } catch (backendError) {
                    // Convert numeric ONNX errors to proper Error objects
                    const errorMessage = typeof backendError === 'number'
                        ? `ONNX runtime error code: ${backendError}`
                        : (backendError?.message || String(backendError));

                    console.warn(`Failed to load with ${backend.device}: ${errorMessage}`);
                    lastError = new Error(`${backend.device} backend failed: ${errorMessage}`);
                }
            }

            // All backends failed
            throw lastError || new Error('Failed to load Whisper model with any backend');

        } catch (error) {
            // Ensure we always have a proper Error object
            const normalizedError = error instanceof Error
                ? error
                : new Error(typeof error === 'number'
                    ? `ONNX runtime error code: ${error}`
                    : String(error));

            console.error('Whisper model load error:', normalizedError);
            this.onError(normalizedError);
            throw normalizedError;
        } finally {
            this.isLoading = false;
        }
    }

    /**
     * Transcribe audio data
     * @param {Float32Array} audioData - Audio samples at 16kHz
     * @returns {Promise<string>} - Transcribed text
     */
    async transcribe(audioData) {
        console.log(`[Whisper] transcribe called, isLoaded: ${this.isLoaded}, audioData length: ${audioData?.length}`);

        if (!this.isLoaded) {
            console.log('[Whisper] Model not loaded, loading now...');
            await this.loadModel();
        }

        try {
            console.log('[Whisper] Calling transcriber pipeline...');
            const result = await this.transcriber(audioData, {
                chunk_length_s: 30,
                stride_length_s: 5,
                return_timestamps: false,
            });

            console.log('[Whisper] Transcription complete:', result);
            return result.text.trim();

        } catch (error) {
            this.onError(error);
            throw error;
        }
    }

    /**
     * Unload the model to free memory
     */
    async unloadModel() {
        if (this.transcriber) {
            // transformers.js doesn't have explicit unload, but we can null the reference
            this.transcriber = null;
            this.isLoaded = false;
        }
    }

    /**
     * Get model loading status
     */
    getStatus() {
        return {
            isLoading: this.isLoading,
            isLoaded: this.isLoaded,
            modelId: this.modelId
        };
    }
}
