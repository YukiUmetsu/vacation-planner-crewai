import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { PlaceDetailPanel } from "./PlaceDetailPanel";

afterEach(() => {
  cleanup();
});

const place = {
  name: "Shibuya",
  place_key: "shibuya",
  category: "other",
};

function Host() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Opener
      </button>
      {open && (
        <PlaceDetailPanel place={place} onClose={() => setOpen(false)} />
      )}
    </div>
  );
}

describe("PlaceDetailPanel a11y", () => {
  it("focuses Close on open, Escape closes, focus returns to opener", async () => {
    const user = userEvent.setup();
    render(<Host />);

    const opener = screen.getByRole("button", { name: "Opener" });
    opener.focus();
    expect(opener).toHaveFocus();

    await user.click(opener);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
