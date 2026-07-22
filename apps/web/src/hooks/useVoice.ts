import { useCallback, useEffect, useRef, useState } from "react";

// Add types for Web Speech API since it's not strictly in standard TS DOM types
declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

export function useVoice(onFinal: (text: string) => void, lang: string = "hi-IN") {
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<any>(null);
  const onFinalRef = useRef(onFinal);

  // Keep callback fresh
  useEffect(() => {
    onFinalRef.current = onFinal;
  }, [onFinal]);

  // Recreated when the language changes so the citizen's choice actually reaches
  // the recogniser — hi-IN transcribes Hindi/Hinglish, en-IN plain English.
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Web Speech API is not supported in this browser.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = lang;

    recognition.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          const finalStr = event.results[i][0].transcript.trim();
          if (finalStr) {
            onFinalRef.current(finalStr);
          }
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      setInterimTranscript(interim);
    };

    recognition.onerror = (event: any) => {
      if (event.error === "no-speech") return;
      setError(event.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      // If we are supposed to be listening but the API stopped (e.g. timeout), restart it.
      setIsListening((currentlyListening) => {
        if (currentlyListening) {
          try {
            recognition.start();
          } catch (e) {
            // Ignore start errors
          }
        }
        return currentlyListening;
      });
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.onend = null;
      recognition.stop();
    };
  }, [lang]);

  const toggle = useCallback(() => {
    if (!recognitionRef.current) return;
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
      setInterimTranscript("");
    } else {
      setInterimTranscript("");
      setError(null);
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (e) {
        console.error(e);
      }
    }
  }, [isListening]);

  const stop = useCallback(() => {
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
      setInterimTranscript("");
    }
  }, [isListening]);

  return { isListening, interimTranscript, error, toggle, stop };
}
