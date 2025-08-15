import { toast } from "sonner@2.0.3";

// Helper functions for consistent toast styling
export const Toast = {
  success: (message: string, description?: string) => {
    toast.success(message, {
      description,
      duration: 4000,
    });
  },

  error: (message: string, description?: string) => {
    toast.error(message, {
      description,
      duration: 0, // Don't auto-dismiss errors
    });
  },

  warning: (message: string, description?: string) => {
    toast.warning(message, {
      description,
      duration: 6000,
    });
  },

  info: (message: string, description?: string) => {
    toast.info(message, {
      description,
      duration: 4000,
    });
  },

  loading: (message: string) => {
    return toast.loading(message);
  },

  dismiss: (toastId?: string | number) => {
    toast.dismiss(toastId);
  },

  // Utility for copy to clipboard with feedback
  copySuccess: (item: string) => {
    toast.success(`Copied to clipboard`, {
      description: `${item} copied successfully`,
      duration: 3000,
    });
  },

  // Utility for save confirmations
  saveSuccess: (item: string = "Changes") => {
    toast.success("Saved", {
      description: `${item} saved successfully`,
      duration: 3000,
    });
  },

  // Utility for connection status
  connectionRestored: () => {
    toast.success("Connection restored", {
      description: "Successfully reconnected to walNUT",
      duration: 4000,
    });
  },

  connectionLost: () => {
    toast.error("Connection lost", {
      description: "Trying to reconnect...",
      duration: 0,
    });
  },
};