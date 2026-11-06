/** One row of the today's-collection popover: colored marker, label, episode count, and an optional duration. */
export function BreakdownRow({
  label,
  count,
  duration,
  dotClass = "bg-transparent",
}: {
  label: string;
  count: number;
  duration?: string;
  dotClass?: string;
}) {
  return (
    <div className="flex items-center gap-2" data-testid={`breakdown-${label}`}>
      <span className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`} />
      <span className="flex-1 text-muted-foreground">{label}</span>
      <span className="tabular-nums text-foreground">{count}</span>
      <span className="w-16 text-right tabular-nums text-muted-foreground">{duration}</span>
    </div>
  );
}
