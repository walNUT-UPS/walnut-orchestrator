import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { LoginForm } from '../components/auth/LoginForm';
import { setAuthRequiredHandler } from '../services/api';

export function AuthPromptProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const waiters = React.useRef<Array<() => void>>([]);

  React.useEffect(() => {
    setAuthRequiredHandler(async () => {
      return new Promise<void>((resolve) => {
        waiters.current.push(resolve);
        setOpen(true);
      });
    });
    return () => setAuthRequiredHandler(async () => {});
  }, []);

  const onSuccess = () => {
    setOpen(false);
    const resolves = waiters.current.splice(0, waiters.current.length);
    resolves.forEach((r) => r());
  };

  return (
    <>
      {children}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Sign in to continue</DialogTitle>
          </DialogHeader>
          <LoginForm onSuccess={onSuccess} />
        </DialogContent>
      </Dialog>
    </>
  );
}
