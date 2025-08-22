import React from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '../ui/sheet';
import { PolicyForm } from './PolicyForm';
import type { PolicySpec } from './types';

export function PolicyFlyout({
  open,
  onOpenChange,
  initial,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initial?: { id?: number; spec?: PolicySpec };
  onSaved?: () => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[720px] max-w-[95vw]">
        <SheetHeader>
          <SheetTitle>{initial?.id ? 'Edit Policy' : 'Create Policy'}</SheetTitle>
          <SheetDescription>Define triggers, targets, and ordered actions.</SheetDescription>
        </SheetHeader>
        <div className="mt-4">
          <PolicyForm initial={initial} onSaved={() => { onSaved?.(); onOpenChange(false); }} onCancel={() => onOpenChange(false)} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

