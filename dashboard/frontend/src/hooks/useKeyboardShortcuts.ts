/**
 * Keyboard shortcuts hook for global navigation
 */

import { useEffect, useCallback, useState, useMemo } from "react";
import { useNavigate, useLocation } from "@tanstack/react-router";

export interface Shortcut {
  key: string;
  description: string;
  action: () => void;
  category: "navigation" | "actions" | "other";
}

interface UseKeyboardShortcutsOptions {
  enabled?: boolean;
  onShowHelp?: () => void;
}

/**
 * Hook to register and handle global keyboard shortcuts
 */
export function useKeyboardShortcuts(
  options: UseKeyboardShortcutsOptions = {},
) {
  const { enabled = true, onShowHelp } = options;
  const navigate = useNavigate();
  const location = useLocation();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  // Define shortcuts - memoized to prevent dependency changes
  const shortcuts: Shortcut[] = useMemo(
    () => [
      {
        key: "g p",
        description: "Go to Projects list",
        action: () => navigate({ to: "/" }),
        category: "navigation",
      },
      {
        key: "g h",
        description: "Go to Home",
        action: () => navigate({ to: "/" }),
        category: "navigation",
      },
      {
        key: "?",
        description: "Show keyboard shortcuts",
        action: () => {
          setIsDialogOpen(true);
          onShowHelp?.();
        },
        category: "other",
      },
      {
        key: "Escape",
        description: "Close dialogs / Cancel",
        action: () => setIsDialogOpen(false),
        category: "other",
      },
    ],
    [navigate, onShowHelp],
  );

  // Track key sequence for multi-key shortcuts (e.g., "g p")
  const [keySequence, setKeySequence] = useState<string[]>([]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled) return;

      // Ignore if typing in an input, textarea, or contenteditable
      const target = event.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      const key = event.key.toLowerCase();

      // Handle single-key shortcuts
      if (key === "?") {
        event.preventDefault();
        setIsDialogOpen(true);
        onShowHelp?.();
        return;
      }

      if (key === "escape") {
        setIsDialogOpen(false);
        setKeySequence([]);
        return;
      }

      // Build key sequence for multi-key shortcuts
      const newSequence = [...keySequence, key].slice(-2);
      setKeySequence(newSequence);

      // Check for matching shortcut
      const sequenceStr = newSequence.join(" ");
      const matchingShortcut = shortcuts.find((s) => s.key === sequenceStr);

      if (matchingShortcut) {
        event.preventDefault();
        matchingShortcut.action();
        setKeySequence([]);
      }

      // Reset sequence after delay
      setTimeout(() => {
        setKeySequence((prev) => (prev.length > 0 ? [] : prev));
      }, 1000);
    },
    [enabled, keySequence, onShowHelp, shortcuts],
  );

  useEffect(() => {
    if (!enabled) return;

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, handleKeyDown]);

  // Reset key sequence on route change
  useEffect(() => {
    setKeySequence([]);
  }, [location.pathname]);

  return {
    shortcuts,
    isDialogOpen,
    setIsDialogOpen,
    keySequence,
  };
}

/**
 * Get shortcuts grouped by category
 */
export function getShortcutsByCategory(shortcuts: Shortcut[]) {
  return shortcuts.reduce(
    (acc, shortcut) => {
      if (!acc[shortcut.category]) {
        acc[shortcut.category] = [];
      }
      acc[shortcut.category].push(shortcut);
      return acc;
    },
    {} as Record<string, Shortcut[]>,
  );
}
