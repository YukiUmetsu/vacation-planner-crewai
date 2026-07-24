import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/http";
import { MetricsPage } from "./MetricsPage";

vi.mock("../auth", () => ({
  isCognitoConfigured: vi.fn(),
  isSignedIn: vi.fn(),
  ensureIdToken: vi.fn(async () => "token"),
  LandingPage: () => <div>Sign in landing</div>,
}));

vi.mock("../api/metrics", () => ({
  listEvalRuns: vi.fn(),
  listOnlineEvents: vi.fn(),
  getEvalRun: vi.fn(),
}));

import {
  ensureIdToken,
  isCognitoConfigured,
  isSignedIn,
} from "../auth";
import { getEvalRun, listEvalRuns, listOnlineEvents } from "../api/metrics";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  vi.mocked(isCognitoConfigured).mockReturnValue(false);
  vi.mocked(isSignedIn).mockReturnValue(false);
  vi.mocked(listEvalRuns).mockResolvedValue({ runs: [] });
  vi.mocked(listOnlineEvents).mockResolvedValue({ kind: "quality", events: [] });
});

describe("MetricsPage", () => {
  it("shows landing when Cognito is configured and user is signed out", () => {
    vi.mocked(isCognitoConfigured).mockReturnValue(true);
    vi.mocked(isSignedIn).mockReturnValue(false);

    render(<MetricsPage />);

    expect(screen.getByText("Sign in landing")).toBeInTheDocument();
    expect(listEvalRuns).not.toHaveBeenCalled();
  });

  it("renders 403 from eval runs load", async () => {
    vi.mocked(listEvalRuns).mockRejectedValue(
      new ApiError(403, "forbidden", "forbidden"),
    );

    render(<MetricsPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/Cognito sub is not in METRICS_ADMIN_SUBS/i),
      ).toBeInTheDocument();
    });
  });

  it("loads eval runs and supports compare selection", async () => {
    const user = userEvent.setup();
    vi.mocked(listEvalRuns).mockResolvedValue({
      runs: [
        {
          run_id: "run-a",
          started_at: "2026-07-19T12:00:00.000000Z",
          experiment_key: "exp1111111111111",
          dimensions: {},
          aggregates: { schema_valid_rate: 1 },
          case_count: 2,
          passed_count: 2,
        },
        {
          run_id: "run-b",
          started_at: "2026-07-19T13:00:00.000000Z",
          experiment_key: "exp1111111111111",
          dimensions: {},
          aggregates: { schema_valid_rate: 0.5 },
          case_count: 2,
          passed_count: 1,
        },
      ],
    });
    vi.mocked(getEvalRun).mockImplementation(async (runId, startedAt) => ({
      run_id: runId,
      started_at: startedAt,
      experiment_key: "exp1111111111111",
      dimensions: {},
      aggregates: { schema_valid_rate: runId === "run-a" ? 1 : 0.5 },
      case_count: 2,
      passed_count: runId === "run-a" ? 2 : 1,
      cases: [],
    }));

    render(<MetricsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText("Select run run-a")).toBeInTheDocument();
      expect(screen.getByLabelText("Select run run-b")).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText("Select run run-a"));
    await user.click(screen.getByLabelText("Select run run-b"));

    await waitFor(() => {
      expect(getEvalRun).toHaveBeenCalledWith(
        "run-a",
        "2026-07-19T12:00:00.000000Z",
      );
      expect(getEvalRun).toHaveBeenCalledWith(
        "run-b",
        "2026-07-19T13:00:00.000000Z",
      );
      expect(screen.getByText(/Compare \(2\)/)).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "run-a" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "run-b" })).toBeInTheDocument();
    });
  });

  it("switches online kind between quality and product", async () => {
    const user = userEvent.setup();
    vi.mocked(listOnlineEvents).mockImplementation(async ({ kind }) => {
      if (kind === "product") {
        return {
          kind: "product",
          events: [
            {
              event_id: "p1",
              occurred_at: "2026-07-19T14:00:00.000000Z",
              event_name: "proposal_accepted",
              trip_id: "t1",
              payload: { source: "ui" },
            },
          ],
        };
      }
      return {
        kind: "quality",
        events: [
          {
            event_id: "q1",
            occurred_at: "2026-07-19T14:00:00.000000Z",
            trip_id: "t1",
            day_index: 1,
            passes_relevance: true,
            crew_name: "day_plan",
            experiment_key: "onlineexp",
          },
        ],
      };
    });

    render(<MetricsPage />);

    await waitFor(() => {
      expect(screen.getByText("day_plan")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText("Kind"), "product");

    await waitFor(() => {
      expect(listOnlineEvents).toHaveBeenCalledWith(
        expect.objectContaining({ kind: "product" }),
      );
      expect(screen.getByText("proposal_accepted")).toBeInTheDocument();
    });
  });

  it("calls ensureIdToken when Cognito session is present", async () => {
    vi.mocked(isCognitoConfigured).mockReturnValue(true);
    vi.mocked(isSignedIn).mockReturnValue(true);

    render(<MetricsPage />);

    await waitFor(() => {
      expect(ensureIdToken).toHaveBeenCalled();
      expect(listEvalRuns).toHaveBeenCalled();
    });
  });
});
