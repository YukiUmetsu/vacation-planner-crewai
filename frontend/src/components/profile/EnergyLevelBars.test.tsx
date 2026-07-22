import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { EnergyLevelBars } from "./EnergyLevelBars";
import type { EnergyLevel } from "../../lib/energyLevel";

afterEach(() => {
  cleanup();
});

function Harness({ initial = 3 as EnergyLevel }: { initial?: EnergyLevel }) {
  const [level, setLevel] = useState<EnergyLevel>(initial);
  return <EnergyLevelBars value={level} onChange={setLevel} />;
}

describe("EnergyLevelBars a11y", () => {
  it("moves selection with arrow keys", async () => {
    const user = userEvent.setup();
    render(<Harness initial={3} />);

    const selected = screen.getByRole("radio", { name: /Energy level 3/i });
    expect(selected).toHaveAttribute("aria-checked", "true");
    selected.focus();

    await user.keyboard("{ArrowRight}");
    expect(
      screen.getByRole("radio", { name: /Energy level 4/i }),
    ).toHaveAttribute("aria-checked", "true");

    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(
      screen.getByRole("radio", { name: /Energy level 2/i }),
    ).toHaveAttribute("aria-checked", "true");

    await user.keyboard("{Home}");
    expect(
      screen.getByRole("radio", { name: /Energy level 1/i }),
    ).toHaveAttribute("aria-checked", "true");

    await user.keyboard("{End}");
    expect(
      screen.getByRole("radio", { name: /Energy level 5/i }),
    ).toHaveAttribute("aria-checked", "true");
  });
});
