import React from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '../ui/sheet';
import { ScrollArea } from '../ui/scroll-area';
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
      <SheetContent className="w-[1400px] max-w-[98vw] p-0">
        <div className="border-b px-6 py-4">
          <SheetHeader>
            <SheetTitle>{initial?.id ? 'Edit Policy' : 'Create Policy'}</SheetTitle>
            <SheetDescription>Define triggers, targets, and ordered actions.</SheetDescription>
          </SheetHeader>
        </div>
        <ScrollArea className="h-[82vh] px-6 py-4">
          <PolicyForm initial={initial} onSaved={() => { onSaved?.(); onOpenChange(false); }} onCancel={() => onOpenChange(false)} />
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
