import { forwardRef, type ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  label?: string;
};

/** Grip control for dnd-kit activators — attach listeners/attributes here only. */
export const DragHandle = forwardRef<HTMLButtonElement, Props>(
  function DragHandle(
    { label = "Drag to reorder", className = "", ...rest },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type="button"
        aria-label={label}
        className={`mt-1 flex h-8 w-6 shrink-0 cursor-grab items-center justify-center rounded text-ink-muted hover:bg-sand hover:text-ink active:cursor-grabbing ${className}`}
        {...rest}
      >
        <span
          aria-hidden
          className="select-none text-sm leading-none tracking-tighter"
        >
          ⋮⋮
        </span>
      </button>
    );
  },
);
