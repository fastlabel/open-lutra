/** Toaster: renders the global toast stack (from the toast store) using Radix Toast. Mounted once at the app root. */

import { CheckCircle2, Info, XCircle } from "lucide-react";
import { type ToastVariant, useToastStore } from "@/stores/toast-store";
import { Toast, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport } from "./toast";

const VARIANT_ICON: Record<ToastVariant, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const remove = useToastStore((s) => s.remove);

  // Radix keeps a hover/focus pause flag in ToastProvider that the viewport only clears while toasts exist,
  // so closing the last toast while hovered would leave every later toast paused. Remounting the provider
  // per non-empty stack resets that flag.
  if (toasts.length === 0) return null;

  return (
    <ToastProvider swipeDirection="up">
      {toasts.map((t) => {
        const Icon = VARIANT_ICON[t.variant];
        return (
          <Toast key={t.id} variant={t.variant} duration={t.duration} onOpenChange={(open) => !open && remove(t.id)}>
            <Icon size={15} className="mt-px flex-none" />
            <div className="flex min-w-0 flex-col gap-0.5">
              <ToastTitle>{t.title}</ToastTitle>
              {t.description && <ToastDescription>{t.description}</ToastDescription>}
            </div>
            <ToastClose />
          </Toast>
        );
      })}
      <ToastViewport />
    </ToastProvider>
  );
}
