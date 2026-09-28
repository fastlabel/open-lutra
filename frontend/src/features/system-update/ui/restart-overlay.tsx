/** Full-screen notice shown while an update restarts the app; reloads once it is back. */

import { Loader2 } from "lucide-react";
import { useEffect } from "react";
import { getHealthCheckUrl } from "@/api/generated/config/config";

const POLL_INTERVAL_MS = 2000;

export function RestartOverlay() {
  // --- Side effects ---
  useEffect(() => {
    let sawDown = false;
    const timer = window.setInterval(async () => {
      const up = await fetch(getHealthCheckUrl(), { cache: "no-store" }).then(
        (res) => res.ok,
        () => false,
      );
      if (!up) {
        sawDown = true;
      } else if (sawDown) {
        window.location.reload();
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div
      role="alert"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-background/90 text-sm"
    >
      <Loader2 size={24} className="animate-spin text-muted-foreground" />
      <p className="font-medium">Updating OpenLUTRA…</p>
      <p className="text-muted-foreground">The page reloads automatically when the update is complete.</p>
    </div>
  );
}
