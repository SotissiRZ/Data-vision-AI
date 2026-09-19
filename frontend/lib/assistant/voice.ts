export type VoiceState =
  | "idle"
  | "requesting_permission"
  | "listening"
  | "speaking"
  | "unsupported"
  | "error";

export type SpeechRecognitionAlternativeLike = {
  transcript: string;
  confidence: number;
};

export type SpeechRecognitionResultLike = {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
};

export type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
};

type RecognitionInstance = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
};

type RecognitionConstructor = new () => RecognitionInstance;

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  }
}

export class BrowserVoiceController {
  private recognition: RecognitionInstance | null = null;
  private continuousRequested = false;
  private manuallyStopped = false;
  private language: string;
  private onFinalText?: (text: string) => void;
  private onState?: (state: VoiceState) => void;

  constructor(options?: {
    language?: string;
    onFinalText?: (text: string) => void;
    onState?: (state: VoiceState) => void;
  }) {
    this.language = options?.language ?? "fr-FR";
    this.onFinalText = options?.onFinalText;
    this.onState = options?.onState;
  }

  isRecognitionSupported() {
    return Boolean(
      typeof window !== "undefined" &&
        (window.SpeechRecognition || window.webkitSpeechRecognition),
    );
  }

  setLanguage(language: string) {
    this.language = language;
    if (this.recognition) this.recognition.lang = language;
  }

  listen(options?: { continuous?: boolean }) {
    if (typeof window === "undefined") return;
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      this.onState?.("unsupported");
      return;
    }

    this.stopSpeaking();
    this.manuallyStopped = false;
    this.continuousRequested = Boolean(options?.continuous);

    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch {}
    }

    const recognition = new Recognition();
    recognition.lang = this.language;
    recognition.continuous = this.continuousRequested;
    recognition.interimResults = true;

    recognition.onstart = () => this.onState?.("listening");

    recognition.onerror = () => {
      this.onState?.("error");
    };

    recognition.onresult = (event) => {
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal && result[0]?.transcript) {
          finalText += result[0].transcript;
        }
      }
      const text = finalText.trim();
      if (text) this.onFinalText?.(text);
    };

    recognition.onend = () => {
      this.onState?.("idle");
      if (this.continuousRequested && !this.manuallyStopped) {
        try {
          recognition.start();
        } catch {}
      }
    };

    this.recognition = recognition;
    this.onState?.("requesting_permission");

    try {
      recognition.start();
    } catch {
      this.onState?.("error");
    }
  }

  stopListening() {
    this.manuallyStopped = true;
    this.continuousRequested = false;
    try {
      this.recognition?.stop();
    } catch {}
    this.onState?.("idle");
  }

  speak(text: string, options?: { language?: string; rate?: number; pitch?: number }) {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      this.onState?.("unsupported");
      return;
    }

    this.stopSpeaking();

    const utterance = new SpeechSynthesisUtterance(sanitizeSpeechText(text));
    utterance.lang = options?.language ?? this.language;
    utterance.rate = options?.rate ?? 1;
    utterance.pitch = options?.pitch ?? 1;

    utterance.onstart = () => this.onState?.("speaking");
    utterance.onend = () => this.onState?.("idle");
    utterance.onerror = () => this.onState?.("error");

    window.speechSynthesis.speak(utterance);
  }

  stopSpeaking() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  }

  destroy() {
    this.stopListening();
    this.stopSpeaking();
    this.recognition = null;
  }
}


function sanitizeSpeechText(text: string): string {
  return text
    .replace(/\(s\)|\(e\)|\(es\)|\(x\)/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}
