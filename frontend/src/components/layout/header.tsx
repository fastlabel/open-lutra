/** Header: brand and navigation on the left, app-wide utilities on the right.
 *
 * The right-hand slot is filled by the root route, so this shared component does not depend on features.
 */

import { Link } from "@tanstack/react-router";
import { FolderOpen } from "lucide-react";
import type { ReactNode } from "react";

type HeaderProps = {
  right?: ReactNode;
};

export function Header({ right }: HeaderProps) {
  return (
    <div className="flex h-11 items-center justify-between border-b border-border bg-background px-4 text-sm">
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
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}
