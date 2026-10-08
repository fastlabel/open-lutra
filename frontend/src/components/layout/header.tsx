/** Header: brand, navigation, and the theme toggle. */

import { Link } from "@tanstack/react-router";
import { FolderOpen, Moon, Sun } from "lucide-react";
import { useThemeStore } from "@/stores/theme-store";

export function Header() {
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

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
      <button
        type="button"
        onClick={toggleTheme}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        className="ml-auto flex cursor-pointer items-center rounded p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
      </button>
    </div>
  );
}
