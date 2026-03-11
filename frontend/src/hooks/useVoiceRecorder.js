import { useState, useRef, useCallback } from "react";

const MAX_DURATION_MS = 120_000;

export default function useVoiceRecorder() {
  const [state, setState] = useState("idle");
  const [elapsed, setElapsed] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [audioBlob, setAudioBlob] = useState(null);

  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const recognitionRef = useRef(null);

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    mediaRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      setAudioBlob(blob);
      stream.getTracks().forEach((t) => t.stop());
      setState("complete");
    };

    recorder.start(250);
    setState("recording");
    setElapsed(0);

    const start = Date.now();
    timerRef.current = setInterval(() => {
      const ms = Date.now() - start;
      setElapsed(ms);
      if (ms >= MAX_DURATION_MS) stopRecording();
    }, 200);

    if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
      const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.onresult = (e) => {
        let text = "";
        for (let i = 0; i < e.results.length; i++) {
          text += e.results[i][0].transcript;
        }
        setTranscript(text);
      };
      recognition.start();
      recognitionRef.current = recognition;
    }
  }, []);

  const stopRecording = useCallback(() => {
    clearInterval(timerRef.current);
    if (mediaRef.current?.state === "recording") {
      mediaRef.current.stop();
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    setState("idle");
    setElapsed(0);
    setTranscript("");
    setAudioBlob(null);
  }, []);

  return {
    state,
    elapsed,
    transcript,
    audioBlob,
    startRecording,
    stopRecording,
    reset,
    maxDuration: MAX_DURATION_MS,
  };
}
