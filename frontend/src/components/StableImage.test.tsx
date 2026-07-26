import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { StableImage } from "./StableImage";

describe("StableImage", () => {
  const OriginalImage = globalThis.Image;

  beforeEach(() => {
    class MockImage {
      onload: ((ev?: Event) => void) | null = null;
      onerror: ((ev?: Event) => void) | null = null;
      referrerPolicy = "";
      private _src = "";
      set src(value: string) {
        this._src = value;
        queueMicrotask(() => {
          if (value.includes("fail")) {
            this.onerror?.(new Event("error"));
          } else {
            this.onload?.(new Event("load"));
          }
        });
      }
      get src() {
        return this._src;
      }
    }
    vi.stubGlobal("Image", MockImage);
  });

  afterEach(() => {
    cleanup();
    vi.stubGlobal("Image", OriginalImage);
  });

  it("does not paint until preload succeeds", async () => {
    render(<StableImage src="https://cdn.example/a.jpg" alt="place" />);
    expect(screen.queryByRole("img")).toBeNull();

    await waitFor(() => {
      expect(screen.getByRole("img").getAttribute("src")).toBe(
        "https://cdn.example/a.jpg",
      );
    });
  });

  it("keeps the previous frame until the new src loads", async () => {
    const { rerender } = render(
      <StableImage src="https://cdn.example/a.jpg" alt="place" />,
    );
    await waitFor(() => {
      expect(screen.getByRole("img").getAttribute("src")).toBe(
        "https://cdn.example/a.jpg",
      );
    });

    rerender(<StableImage src="https://cdn.example/b.jpg" alt="place" />);
    expect(screen.getByRole("img").getAttribute("src")).toBe(
      "https://cdn.example/a.jpg",
    );

    await waitFor(() => {
      expect(screen.getByRole("img").getAttribute("src")).toBe(
        "https://cdn.example/b.jpg",
      );
    });
  });

  it("clears the frame and calls onDisplayError when a pending src fails", async () => {
    const onDisplayError = vi.fn();
    const { rerender } = render(
      <StableImage
        src="https://cdn.example/a.jpg"
        alt="place"
        onDisplayError={onDisplayError}
      />,
    );
    await waitFor(() => {
      expect(screen.getByRole("img")).toBeTruthy();
    });

    await act(async () => {
      rerender(
        <StableImage
          src="https://cdn.example/fail-b.jpg"
          alt="other"
          onDisplayError={onDisplayError}
        />,
      );
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onDisplayError).toHaveBeenCalled();
      expect(screen.queryByRole("img")).toBeNull();
    });
  });

  it("never paints a src that fails on first load", async () => {
    const onDisplayError = vi.fn();
    render(
      <StableImage
        src="https://cdn.example/fail.jpg"
        alt="place"
        onDisplayError={onDisplayError}
      />,
    );

    await waitFor(() => {
      expect(onDisplayError).toHaveBeenCalled();
    });
    expect(screen.queryByRole("img")).toBeNull();
  });
});
