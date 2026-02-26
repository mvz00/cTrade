import { Info } from 'lucide-react';

interface InfoTooltipProps {
  text: string;
}

export function InfoTooltip({ text }: InfoTooltipProps) {
  return (
    <span className="group/tip relative inline-flex ml-1 align-middle">
      <Info
        size={14}
        className="text-ct-text-dim hover:text-ct-text-muted cursor-help transition-colors"
      />
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-max max-w-[250px] rounded-lg border border-ct-border bg-ct-bg-card px-3 py-2 text-xs text-ct-text shadow-lg opacity-0 transition-opacity group-hover/tip:opacity-100 z-50">
        {text}
        {/* Arrow */}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-ct-border" />
      </span>
    </span>
  );
}
