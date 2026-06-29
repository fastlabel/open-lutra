/** Recordings page: table of recordings. */

import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { RecordingsTable } from "@/features/recordings-table";
import { useFileEntries } from "@/hooks/use-file-entries";

function RecordingsPage() {
  // --- Server state (TanStack Query) ---
  const entries = useFileEntries();

  return (
    <div className="flex h-full flex-col">
      {/* Recordings header */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <Link
            to="/"
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ArrowLeft size={16} />
          </Link>
          <span className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Recordings
          </span>
          <Badge variant="secondary" className="h-5 px-1.5 text-xs">
            {entries.length}
          </Badge>
        </div>
      </div>

      {/* Main content: the table (it owns its own scroll container for virtualization) */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <RecordingsTable entries={entries} />
      </div>
    </div>
  );
}

export const Route = createFileRoute("/recordings")({
  component: RecordingsPage,
});
