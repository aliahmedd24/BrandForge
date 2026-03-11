import { Mic, Square, RotateCcw, Check } from "lucide-react";
import useVoiceRecorder from "../../hooks/useVoiceRecorder";

function formatTime(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export default function VoiceBriefRecorder({ onComplete }) {
  const {
    state,
    elapsed,
    transcript,
    audioBlob,
    startRecording,
    stopRecording,
    reset,
    maxDuration,
  } = useVoiceRecorder();

  const handleComplete = () => {
    if (audioBlob) onComplete(audioBlob, transcript);
  };

  return (
    <div className="glass-panel p-4 space-y-3">
      <div className="flex items-center gap-3">
        {state === "idle" && (
          <button
            type="button"
            onClick={startRecording}
            aria-label="Start recording voice brief"
            className="flex items-center gap-2 px-4 py-2 bg-brand-surface border border-brand-border rounded-lg hover:border-brand-accent/50 transition-colors text-sm"
          >
            <Mic size={16} className="text-brand-accent" />
            Speak Your Brief
          </button>
        )}

        {state === "recording" && (
          <>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 bg-brand-danger rounded-full animate-pulse" />
              <span className="text-sm font-medium tabular-nums">
                {formatTime(elapsed)}
              </span>
              {elapsed > maxDuration - 30_000 && (
                <span className="text-xs text-brand-danger">
                  {formatTime(maxDuration - elapsed)} left
                </span>
              )}
            </div>

            {/* Waveform bars */}
            <div className="flex items-center gap-0.5 h-6" aria-hidden="true">
              {Array.from({ length: 12 }).map((_, i) => (
                <div
                  key={i}
                  className="w-1 bg-brand-accent rounded-full animate-pulse"
                  style={{
                    height: `${8 + Math.random() * 16}px`,
                    animationDelay: `${i * 0.08}s`,
                  }}
                />
              ))}
            </div>

            <button
              type="button"
              onClick={stopRecording}
              aria-label="Stop recording"
              className="ml-auto p-2 bg-brand-danger/20 text-brand-danger rounded-lg hover:bg-brand-danger/30 transition-colors"
            >
              <Square size={16} />
            </button>
          </>
        )}

        {state === "complete" && (
          <div className="flex items-center gap-2 w-full">
            <Check size={16} className="text-brand-success" />
            <span className="text-sm text-brand-success font-medium">
              Recorded ({formatTime(elapsed)})
            </span>
            <div className="ml-auto flex gap-2">
              <button
                type="button"
                onClick={reset}
                aria-label="Re-record"
                className="p-2 text-brand-muted hover:text-white transition-colors"
              >
                <RotateCcw size={14} />
              </button>
              <button
                type="button"
                onClick={handleComplete}
                className="px-3 py-1 text-sm bg-brand-accent rounded-lg hover:bg-brand-accent-hover transition-colors"
              >
                Use Recording
              </button>
            </div>
          </div>
        )}
      </div>

      {transcript && state !== "idle" && (
        <p className="text-xs text-brand-muted italic line-clamp-2">
          "{transcript}"
        </p>
      )}
    </div>
  );
}
