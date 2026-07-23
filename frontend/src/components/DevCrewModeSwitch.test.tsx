import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DevCrewModeSwitch } from "./DevCrewModeSwitch";
import { getDevCrewMode } from "../lib/devCrewMode";

afterEach(() => {
  cleanup();
  localStorage.removeItem("vp.devCrewMode");
  vi.unstubAllEnvs();
});

describe("DevCrewModeSwitch", () => {
  it("renders nothing outside Vite DEV", () => {
    vi.stubEnv("DEV", false);
    const { container } = render(<DevCrewModeSwitch />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows current mode and toggles fake ↔ agentcore in DEV", async () => {
    vi.stubEnv("DEV", true);
    const user = userEvent.setup();
    render(<DevCrewModeSwitch />);

    expect(screen.getByTestId("dev-crew-mode-switch")).toBeInTheDocument();
    expect(screen.getByTestId("dev-crew-mode-current")).toHaveTextContent("Fake");
    expect(screen.getByText(/Currently:/)).toBeInTheDocument();
    expect(getDevCrewMode()).toBe("fake");

    await user.click(screen.getByRole("button", { name: "AgentCore" }));
    expect(getDevCrewMode()).toBe("agentcore");
    expect(screen.getByTestId("dev-crew-mode-current")).toHaveTextContent(
      "AgentCore",
    );

    await user.click(screen.getByRole("button", { name: "Fake" }));
    expect(getDevCrewMode()).toBe("fake");
    expect(screen.getByTestId("dev-crew-mode-current")).toHaveTextContent("Fake");
  });
});
