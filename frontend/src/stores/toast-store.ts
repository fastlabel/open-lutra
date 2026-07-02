/** Global toast notification store.
 *
 * Holds the active toast stack and exposes an imperative `toast` helper so
 * non-React callers (mutation observers, other stores) can raise notifications.
 * The <Toaster /> component subscribes to this store and renders each toast with
 * Radix Toast, which owns the auto-dismiss timer, pause-on-hover, and swipe-to-dismiss.
 */
import { create } from "zustand";

export type ToastVariant = "success" | "error" | "info";

/** Default auto-dismiss duration in milliseconds. */
export const TOAST_DURATION_MS = 5000;
/** Maximum number of toasts shown at once (older toasts drop off the stack). */
export const TOAST_LIMIT = 4;

export interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
  duration: number;
}

interface ToastStore {
  toasts: ToastItem[];
  /** Push a toast onto the stack and return its id. */
  add: (toast: Omit<ToastItem, "id">) => string;
  /** Remove a toast (called once Radix reports it closed). */
  remove: (id: string) => void;
}

let counter = 0;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  add: (toast) => {
    const id = `toast-${++counter}`;
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }].slice(-TOAST_LIMIT) }));
    return id;
  },
  remove: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

/** Imperative helper usable from anywhere (React components or plain modules). */
export const toast = {
  success: (title: string, description?: string) =>
    useToastStore.getState().add({ title, description, variant: "success", duration: TOAST_DURATION_MS }),
  error: (title: string, description?: string) =>
    useToastStore.getState().add({ title, description, variant: "error", duration: TOAST_DURATION_MS }),
  info: (title: string, description?: string) =>
    useToastStore.getState().add({ title, description, variant: "info", duration: TOAST_DURATION_MS }),
};
