/**
 * IntentDetector - Detects if transcribed text is a question for ActionSync
 *
 * Uses wake word detection and question pattern matching.
 * No external API calls - all detection happens locally.
 */

export class IntentDetector {
    constructor(options = {}) {
        // Wake words (case-insensitive)
        this.wakeWords = options.wakeWords || [
            'action sync',
            'actionsync',
            'hey action sync',
            'hey actionsync',
            'ok action sync',
            'ok actionsync',
        ];

        // Question starters
        this.questionStarters = [
            'what', 'how', 'why', 'when', 'where', 'who', 'which',
            'is there', 'are there', 'is it', 'are we', 'do we', 'does',
            'can you', 'could you', 'would you', 'will you',
            'can we', 'could we', 'should we',
            'tell me', 'show me', 'find', 'search', 'look up',
            'explain', 'describe', 'list',
        ];

        // Confidence thresholds
        this.wakeWordConfidence = 0.9;
        this.questionPatternConfidence = 0.7;
        this.minConfidenceThreshold = options.minConfidenceThreshold || 0.6;
    }

    /**
     * Detect if text is a question for ActionSync
     * @param {string} text - Transcribed text
     * @returns {{ isQuestion: boolean, confidence: number, cleanedText: string }}
     */
    detect(text) {
        if (!text || typeof text !== 'string') {
            return { isQuestion: false, confidence: 0, cleanedText: '' };
        }

        const lowerText = text.toLowerCase().trim();

        // REQUIRE wake word - only process if "ActionSync" is mentioned
        const wakeWordResult = this.checkWakeWord(lowerText);
        if (wakeWordResult.found) {
            const textAfter = wakeWordResult.textAfterWakeWord;

            // Need some actual content after the wake word
            if (textAfter && textAfter.length > 3) {
                return {
                    isQuestion: true,
                    confidence: this.wakeWordConfidence,
                    cleanedText: textAfter,
                    reason: 'wake_word'
                };
            } else {
                // Wake word detected but no question yet - wait for more
                return {
                    isQuestion: false,
                    confidence: 0.3,
                    cleanedText: text.trim(),
                    reason: 'wake_word_only'
                };
            }
        }

        // No wake word - don't process (just log the transcription)
        return {
            isQuestion: false,
            confidence: 0,
            cleanedText: text.trim(),
            reason: 'no_wake_word'
        };
    }

    /**
     * Check if text contains a wake word
     */
    checkWakeWord(text) {
        for (const wakeWord of this.wakeWords) {
            const index = text.indexOf(wakeWord);
            if (index !== -1) {
                // Extract text after wake word
                let textAfter = text.slice(index + wakeWord.length).trim();

                // Remove common punctuation/filler after wake word
                textAfter = textAfter.replace(/^[,.\s]+/, '').trim();

                return {
                    found: true,
                    wakeWord: wakeWord,
                    textAfterWakeWord: textAfter || text // fallback to full text if nothing after
                };
            }
        }

        return { found: false };
    }

    /**
     * Check if text matches question patterns
     */
    checkQuestionPattern(text) {
        let confidence = 0;
        let reasons = [];

        // Check if ends with question mark
        if (text.endsWith('?')) {
            confidence += 0.4;
            reasons.push('ends_with_question_mark');
        }

        // Check if starts with question word
        for (const starter of this.questionStarters) {
            if (text.startsWith(starter + ' ') || text.startsWith(starter + ',')) {
                confidence += 0.4;
                reasons.push(`starts_with_${starter}`);
                break;
            }
        }

        // Check for interrogative structure
        if (this.hasInterrogativeStructure(text)) {
            confidence += 0.2;
            reasons.push('interrogative_structure');
        }

        // Cap confidence at 0.85 for pattern matching (wake word is higher)
        confidence = Math.min(confidence, 0.85);

        return {
            isQuestion: confidence >= this.minConfidenceThreshold,
            confidence: confidence,
            reasons: reasons
        };
    }

    /**
     * Check for interrogative sentence structure
     */
    hasInterrogativeStructure(text) {
        // Inverted verb-subject patterns
        const invertedPatterns = [
            /^(is|are|was|were|do|does|did|can|could|will|would|should|have|has|had)\s+\w+/i,
        ];

        for (const pattern of invertedPatterns) {
            if (pattern.test(text)) {
                return true;
            }
        }

        return false;
    }

    /**
     * Add custom wake word
     */
    addWakeWord(word) {
        const normalized = word.toLowerCase().trim();
        if (!this.wakeWords.includes(normalized)) {
            this.wakeWords.push(normalized);
        }
    }

    /**
     * Remove wake word
     */
    removeWakeWord(word) {
        const normalized = word.toLowerCase().trim();
        const index = this.wakeWords.indexOf(normalized);
        if (index !== -1) {
            this.wakeWords.splice(index, 1);
        }
    }

    /**
     * Get current configuration
     */
    getConfig() {
        return {
            wakeWords: [...this.wakeWords],
            questionStarters: [...this.questionStarters],
            minConfidenceThreshold: this.minConfidenceThreshold
        };
    }
}
