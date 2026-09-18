export type VoiceTranscript = {
  text: string;
  final: boolean;
  confidence?: number;
};

export interface SpeechToTextProvider {
  readonly id: string;
  isSupported(): boolean;
  start(options: {
    language: string;
    continuous: boolean;
    onTranscript: (value: VoiceTranscript) => void;
    onError: (error: Error) => void;
  }): Promise<void> | void;
  stop(): Promise<void> | void;
}

export interface TextToSpeechProvider {
  readonly id: string;
  isSupported(): boolean;
  speak(options: {
    text: string;
    language: string;
    rate?: number;
    pitch?: number;
    onStart?: () => void;
    onEnd?: () => void;
    onError?: (error: Error) => void;
  }): Promise<void> | void;
  stop(): Promise<void> | void;
}

/**
 * The current v2.13 UI uses the browser provider through voice.ts.
 *
 * Production implementations can add:
 *
 * - LocalWhisperSTTProvider
 * - LocalTTSProvider
 * - OpenAICompatibleRealtimeProvider
 * - EnterpriseCloudVoiceProvider
 *
 * Provider selection belongs to DataVision settings and privacy policy.
 */
