export default function LoadingShimmer({
  className = "",
  height = "h-40",
  rounded = "rounded-xl",
}) {
  return (
    <div
      className={`${height} ${rounded} bg-gradient-to-r from-brand-surface via-brand-border to-brand-surface bg-[length:200%_100%] animate-shimmer ${className}`}
      role="status"
      aria-label="Loading"
    >
      <span className="sr-only">Loading...</span>
    </div>
  );
}
