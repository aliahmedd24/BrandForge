import { useEffect, useRef, useState } from "react";

export default function StreamingText({ text, speed = 20, className = "" }) {
  const [displayed, setDisplayed] = useState("");
  const indexRef = useRef(0);

  useEffect(() => {
    if (!text) return;
    indexRef.current = 0;
    setDisplayed("");

    const interval = setInterval(() => {
      indexRef.current += 1;
      if (indexRef.current >= text.length) {
        setDisplayed(text);
        clearInterval(interval);
      } else {
        setDisplayed(text.slice(0, indexRef.current));
      }
    }, speed);

    return () => clearInterval(interval);
  }, [text, speed]);

  return (
    <span className={className}>
      {displayed}
      {displayed.length < (text?.length || 0) && (
        <span className="inline-block w-0.5 h-4 bg-brand-accent animate-pulse ml-0.5 align-middle" />
      )}
    </span>
  );
}
