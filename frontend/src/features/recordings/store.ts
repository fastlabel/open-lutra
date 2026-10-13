/** State management for recording-list check status. */
import { create } from "zustand";
import { devtools } from "zustand/middleware";
import { applyRange } from "./range-select";

interface RecordingsStore {
  /** Set of checked folder names */
  checkedFolders: Set<string>;
  /** Row last toggled by a plain click: the start of the next Shift+click range. */
  anchorFolder: string | null;
  /** Plain click on a row checkbox: toggle it and make it the range anchor. */
  toggleCheck: (folder: string) => void;
  /** Shift+click on a row checkbox: apply the anchor's state to every displayed row up to `folder`. */
  checkRange: (displayedFolders: string[], folder: string) => void;
  toggleCheckAll: (allFolders: string[]) => void;
  /** Replace the check state entirely with the given folders (used when switching filter tabs) */
  setCheckedFolders: (folders: string[]) => void;
  clearChecked: () => void;
}

export const useRecordingsStore = create<RecordingsStore>()(
  devtools(
    (set, get) => ({
      checkedFolders: new Set(),
      anchorFolder: null,
      toggleCheck: (folder) =>
        set(
          (state) => {
            const next = new Set(state.checkedFolders);
            if (next.has(folder)) next.delete(folder);
            else next.add(folder);
            return { checkedFolders: next, anchorFolder: folder };
          },
          false,
          "toggleCheck",
        ),
      checkRange: (displayedFolders, folder) => {
        const { checkedFolders, anchorFolder, toggleCheck } = get();
        const next = applyRange(checkedFolders, displayedFolders, anchorFolder, folder);
        if (next) set({ checkedFolders: next }, false, "checkRange");
        else toggleCheck(folder);
      },
      toggleCheckAll: (allFolders) =>
        set(
          (state) => {
            const allChecked = allFolders.length > 0 && allFolders.every((f) => state.checkedFolders.has(f));
            return { checkedFolders: allChecked ? new Set() : new Set(allFolders), anchorFolder: null };
          },
          false,
          "toggleCheckAll",
        ),
      setCheckedFolders: (folders) =>
        set({ checkedFolders: new Set(folders), anchorFolder: null }, false, "setCheckedFolders"),
      clearChecked: () => set({ checkedFolders: new Set(), anchorFolder: null }, false, "clearChecked"),
    }),
    { name: "RecordingsStore" },
  ),
);
