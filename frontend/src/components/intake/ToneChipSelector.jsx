const TONE_OPTIONS = [
  "bold",
  "minimal",
  "playful",
  "luxurious",
  "sustainable",
  "urban",
  "edgy",
  "warm",
  "professional",
  "rebellious",
  "nostalgic",
  "futuristic",
];

export default function ToneChipSelector({ selected, onChange }) {
  const toggle = (tone) => {
    if (selected.includes(tone)) {
      onChange(selected.filter((t) => t !== tone));
    } else {
      onChange([...selected, tone]);
    }
  };

  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Tone keywords">
      {TONE_OPTIONS.map((tone) => {
        const active = selected.includes(tone);
        return (
          <button
            key={tone}
            type="button"
            onClick={() => toggle(tone)}
            aria-pressed={active}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-200
              ${
                active
                  ? "bg-brand-accent text-white shadow-lg shadow-brand-accent/25"
                  : "bg-brand-surface text-brand-muted border border-brand-border hover:border-brand-accent/50 hover:text-white"
              }`}
          >
            {tone}
          </button>
        );
      })}
    </div>
  );
}
