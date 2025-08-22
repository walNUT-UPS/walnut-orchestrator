import React from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../ui/sheet';

export function JsonPreviewDrawer({ open, onOpenChange, data }: { open: boolean; onOpenChange: (v: boolean) => void; data: any }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[640px] max-w-[95vw]">
        <SheetHeader>
          <SheetTitle>Policy JSON</SheetTitle>
        </SheetHeader>
        <pre className="mt-4 text-xs font-mono bg-muted/30 border rounded-md p-3 overflow-auto h-[80vh]">{JSON.stringify(data, null, 2)}</pre>
      </SheetContent>
    </Sheet>
  );
}

