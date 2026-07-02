/** shadcn/ui Toast component (Radix UI based). Renders transient notifications in the corner viewport. */

import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import { Toast as ToastPrimitive } from "radix-ui";
import type * as React from "react";
import { cn } from "@/lib/utils";

const ToastProvider = ToastPrimitive.Provider;

function ToastViewport({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Viewport>) {
  return (
    <ToastPrimitive.Viewport
      data-slot="toast-viewport"
      className={cn(
        "fixed top-2 left-1/2 z-[100] flex max-h-screen w-full max-w-sm -translate-x-1/2 flex-col items-center gap-2 px-4",
        className,
      )}
      {...props}
    />
  );
}

const toastVariants = cva(
  "group pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-md border p-4 pr-9 shadow-lg data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-full data-[state=closed]:animate-out data-[state=closed]:fade-out-80 data-[swipe=move]:translate-y-[var(--radix-toast-swipe-move-y)] data-[swipe=cancel]:translate-y-0 data-[swipe=cancel]:transition-transform data-[swipe=end]:translate-y-[var(--radix-toast-swipe-end-y)]",
  {
    variants: {
      variant: {
        info: "border-border bg-popover text-popover-foreground",
        success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
        error: "border-destructive/40 bg-destructive/15 text-foreground",
      },
    },
    defaultVariants: { variant: "info" },
  },
);

function Toast({
  className,
  variant,
  ...props
}: React.ComponentProps<typeof ToastPrimitive.Root> & VariantProps<typeof toastVariants>) {
  return <ToastPrimitive.Root data-slot="toast" className={cn(toastVariants({ variant }), className)} {...props} />;
}

function ToastTitle({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Title>) {
  return (
    <ToastPrimitive.Title data-slot="toast-title" className={cn("text-[13px] font-semibold", className)} {...props} />
  );
}

function ToastDescription({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Description>) {
  return (
    <ToastPrimitive.Description
      data-slot="toast-description"
      className={cn("text-[13px] opacity-90", className)}
      {...props}
    />
  );
}

function ToastClose({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Close>) {
  return (
    <ToastPrimitive.Close
      data-slot="toast-close"
      aria-label="Close"
      className={cn(
        "absolute right-2 top-2 rounded-md p-0.5 opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus:ring-1 focus:ring-ring",
        className,
      )}
      {...props}
    >
      <X size={14} />
    </ToastPrimitive.Close>
  );
}

export { Toast, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport };
