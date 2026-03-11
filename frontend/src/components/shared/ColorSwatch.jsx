export default function ColorSwatch({ color, label, size = "md" }) {
  const sizes = {
    sm: "w-6 h-6",
    md: "w-10 h-10",
    lg: "w-14 h-14",
  };

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={`${sizes[size]} rounded-lg border border-brand-border shadow-inner`}
        style={{ backgroundColor: color }}
        aria-label={`Color swatch: ${label || color}`}
        role="img"
      />
      {label && (
        <span className="text-[10px] text-brand-muted uppercase tracking-wider">
          {label}
        </span>
      )}
      <span className="text-[10px] text-brand-muted font-mono">{color}</span>
    </div>
  );
}
