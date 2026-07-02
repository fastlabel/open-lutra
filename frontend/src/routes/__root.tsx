/** Root layout: places the Header on every page.
 *
 * The StatusBar (footer) is shown only in dev mode (for connection status, memory usage, and the DevTools toggle).
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { createRootRoute, Outlet } from "@tanstack/react-router";
import { Header } from "@/components/layout/header";
import { StatusBar } from "@/components/layout/StatusBar";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useJobsStream } from "@/hooks/use-jobs-stream";
import { isDevMode } from "@/lib/dev-mode";
import { queryClient } from "@/lib/query-client";
import { usePanelStore } from "@/stores/panel-store";

/** Inner layout that runs under the QueryClientProvider.
 *
 * Hooks that use TanStack Query (such as `useJobsStream`) must be called
 * inside the Provider, so they cannot live in the same component as the Provider itself.
 */
function RootLayoutInner() {
  // Job queue SSE connection (shared by the preview panel and the future footer Jobs panel).
  useJobsStream();

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex h-screen flex-col bg-background">
        <Header />
        <div className="flex-1 overflow-hidden">
          <Outlet />
        </div>
        {/* StatusBar is shown only in dev mode (VITE_DEV_MODE=true). */}
        {isDevMode() && <StatusBar />}
      </div>
      <Toaster />
    </TooltipProvider>
  );
}

function RootLayout() {
  const showQueryDevtools = usePanelStore((s) => s.showQueryDevtools);

  return (
    <QueryClientProvider client={queryClient}>
      <RootLayoutInner />
      {showQueryDevtools && <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />}
    </QueryClientProvider>
  );
}

export const Route = createRootRoute({
  component: RootLayout,
});
