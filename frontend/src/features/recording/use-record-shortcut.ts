/** Keyboard shortcut: Space toggles recording start/stop, mirroring the Record button.
 *
 * Mounted by RecordButton, which renders only on the recorder page, so the shortcut is
 * scoped to that page and torn down on navigation. Targets hands-free operation (e.g. a
 * foot pedal that emits Space) per issue #34.
 *
 * Always live: `toggle()` carries its own connection and selected-topic guards, and cancelling
 * the keydown default suppresses the native Space-to-click, so a focused Record button toggles
 * once.
 */

import { useRecordingStore } from "./store";
import { usePageShortcut } from "./use-page-shortcut";

export function useRecordShortcut(): void {
  usePageShortcut({ code: "Space", onFire: () => useRecordingStore.getState().toggle() });
}
