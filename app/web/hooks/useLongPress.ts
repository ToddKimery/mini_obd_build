"use client";
import { useCallback, useRef } from "react";

export function useLongPress(onLongPress: () => void, delay = 500) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fired = useRef(false);

  const start = useCallback(() => {
    fired.current = false;
    timer.current = setTimeout(() => {
      fired.current = true;
      onLongPress();
    }, delay);
  }, [onLongPress, delay]);

  const cancel = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return {
    /** Spread onto the pressable element. */
    pressProps: {
      onTouchStart:  start,
      onTouchEnd:    cancel,
      onTouchMove:   cancel,   // scrolling — abort
      onMouseDown:   start,
      onMouseUp:     cancel,
      onMouseLeave:  cancel,
    },
    /** True if the most recent press was a long press (use in onClick to suppress navigation). */
    didFire: () => fired.current,
  };
}
