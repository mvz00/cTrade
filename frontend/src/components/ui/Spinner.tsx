import { cn } from '@/lib/cn';

export function Spinner({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center justify-center py-12', className)}>
      <div className="w-8 h-8 border-2 border-ct-border border-t-ct-accent rounded-full animate-spin" />
    </div>
  );
}
