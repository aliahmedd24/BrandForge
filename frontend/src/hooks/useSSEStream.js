import { useEffect, useRef, useState } from "react";
import { createSSEConnection } from "../lib/api";

export default function useSSEStream(campaignId) {
  const [chunks, setChunks] = useState([]);
  const textRef = useRef("");
  const sourceRef = useRef(null);

  useEffect(() => {
    if (!campaignId) return;

    const source = createSSEConnection(campaignId);
    sourceRef.current = source;

    source.addEventListener("text_chunk", (e) => {
      const data = JSON.parse(e.data);
      textRef.current += data.text;
      setChunks((prev) => [...prev, data]);
    });

    source.addEventListener("agent_event", (e) => {
      const data = JSON.parse(e.data);
      setChunks((prev) => [...prev, { type: "event", ...data }]);
    });

    source.onerror = () => {
      source.close();
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [campaignId]);

  return { chunks, fullText: textRef.current };
}
