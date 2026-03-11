import { useState, useEffect } from "react";
import { Server } from "lucide-react";
import { fetchInfraStatus } from "../../lib/api";

export default function InfraStatusPanel() {
  const [data, setData] = useState(null);

  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        const result = await fetchInfraStatus();
        if (active) setData(result);
      } catch (e) {
        console.error("Infra status poll failed:", e);
      }
    }

    poll();
    const interval = setInterval(poll, 10000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  if (!data) return null;

  return (
    <div className="glass-panel p-4 m-3 space-y-3">
      <div className="flex items-center gap-2">
        <Server size={14} className="text-brand-accent" />
        <span className="text-[11px] uppercase tracking-wider text-brand-accent font-semibold">
          Infrastructure
        </span>
        <span className="ml-auto text-[10px] text-brand-muted font-mono">
          {data.project_id}
        </span>
      </div>

      <div className="space-y-1.5">
        {data.services.map((svc) => (
          <div key={svc.name} className="flex items-center gap-2 text-xs">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-success opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-success" />
            </span>
            <span className="text-brand-muted flex-1">{svc.name}</span>
            <span className="text-brand-success font-mono text-[10px]">
              {svc.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
