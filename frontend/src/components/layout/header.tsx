/** Header: brand, navigation, and the software update button. */

import { Link } from "@tanstack/react-router";
import { FolderOpen } from "lucide-react";
import { SystemUpdateButton } from "@/features/system-update";

export function Header() {
  return (
    <div className="flex h-11 items-center border-b border-border bg-background px-4 text-sm">
      <div className="flex items-center gap-2.5">
        <Link to="/" className="no-underline">
          <span className="select-none bg-linear-to-r from-[#D4514A] to-[#B3262D] bg-clip-text text-sm font-bold tracking-[0.18em] text-transparent">
            OpenLUTRA
          </span>
        </Link>
        <Link
          to="/recordings"
          className="flex items-center gap-1.5 rounded px-1.5 py-1 text-sm font-medium text-muted-foreground no-underline transition-colors hover:bg-muted hover:text-foreground data-[status=active]:text-foreground"
          activeProps={{ "data-status": "active" }}
        >
          <FolderOpen size={14} />
          Recordings
        </Link>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <SystemUpdateButton />
      </div>
    </div>
  );
}
