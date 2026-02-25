import { useCallback, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from './Button';
import { AlertTriangle } from 'lucide-react';

/* ------------------------------------------------------------------ */
/*  ConfirmDialog — styled replacement for window.confirm()           */
/* ------------------------------------------------------------------ */

interface ConfirmDialogProps {
  open: boolean;
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'primary' | 'danger';
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'primary',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />
      {/* Dialog */}
      <div className="relative bg-ct-bg-card border border-ct-border rounded-xl shadow-2xl p-6 max-w-md w-full mx-4 animate-in fade-in zoom-in-95 duration-150">
        {title && (
          <div className="flex items-center gap-2 mb-3">
            {variant === 'danger' && (
              <AlertTriangle size={18} className="text-ct-red flex-shrink-0" />
            )}
            <h3 className="text-base font-semibold text-ct-text">{title}</h3>
          </div>
        )}
        <p className="text-sm text-ct-text-muted mb-6 leading-relaxed">{message}</p>
        <div className="flex items-center justify-end gap-3">
          <Button variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={variant === 'danger' ? 'danger' : 'primary'} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/* ------------------------------------------------------------------ */
/*  useConfirm() — async hook that replaces window.confirm()          */
/*                                                                    */
/*  Usage:                                                            */
/*    const { confirm, dialogProps } = useConfirm();                  */
/*    // In JSX: <ConfirmDialog {...dialogProps} />                   */
/*    // In handler: const ok = await confirm({ message: '...' });    */
/* ------------------------------------------------------------------ */

interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'primary' | 'danger';
}

export function useConfirm() {
  const [state, setState] = useState<ConfirmOptions & { open: boolean }>({
    open: false,
    message: '',
  });

  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      setState({ ...options, open: true });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
    resolveRef.current?.(true);
    resolveRef.current = null;
  }, []);

  const handleCancel = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
    resolveRef.current?.(false);
    resolveRef.current = null;
  }, []);

  const dialogProps: ConfirmDialogProps = {
    open: state.open,
    title: state.title,
    message: state.message,
    confirmLabel: state.confirmLabel,
    cancelLabel: state.cancelLabel,
    variant: state.variant,
    onConfirm: handleConfirm,
    onCancel: handleCancel,
  };

  return { confirm, dialogProps };
}
