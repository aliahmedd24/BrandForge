import {
  Instagram,
  Linkedin,
  Twitter,
  Facebook,
  Youtube,
  Music2,
} from "lucide-react";

const PLATFORMS = [
  { id: "instagram", label: "Instagram", Icon: Instagram },
  { id: "linkedin", label: "LinkedIn", Icon: Linkedin },
  { id: "tiktok", label: "TikTok", Icon: Music2 },
  { id: "twitter_x", label: "X", Icon: Twitter },
  { id: "facebook", label: "Facebook", Icon: Facebook },
  { id: "youtube", label: "YouTube", Icon: Youtube },
];

export default function PlatformSelector({ selected, onChange }) {
  const toggle = (id) => {
    if (selected.includes(id)) {
      onChange(selected.filter((p) => p !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  return (
    <div className="flex flex-wrap gap-3" role="group" aria-label="Target platforms">
      {PLATFORMS.map(({ id, label, Icon }) => {
        const active = selected.includes(id);
        return (
          <button
            key={id}
            type="button"
            onClick={() => toggle(id)}
            aria-pressed={active}
            aria-label={label}
            className={`flex flex-col items-center gap-1.5 p-3 rounded-xl transition-all duration-200
              ${
                active
                  ? "bg-brand-accent/15 border-2 border-brand-accent text-brand-accent"
                  : "bg-brand-surface border-2 border-brand-border text-brand-muted hover:border-brand-accent/30 hover:text-white"
              }`}
          >
            <Icon size={22} />
            <span className="text-[11px] font-medium">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
