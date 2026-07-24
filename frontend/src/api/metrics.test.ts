import { beforeEach, describe, expect, it, vi } from "vitest";
import { getEvalRun, listEvalRuns, listOnlineEvents } from "./metrics";

describe("metrics api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
  });

  it("listEvalRuns encodes experiment_key", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ runs: [] }), { status: 200 }),
    );

    await listEvalRuns({ experimentKey: "abc/def+ghi", limit: 10 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/metrics/runs?experiment_key=abc%2Fdef%2Bghi&limit=10",
      expect.any(Object),
    );
  });

  it("getEvalRun encodes started_at and run_id", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run/1",
          started_at: "2026-07-19T15:00:00.000000Z",
          experiment_key: "k",
          dimensions: {},
          aggregates: {},
          case_count: 0,
          passed_count: 0,
        }),
        { status: 200 },
      ),
    );

    await getEvalRun("run/1", "2026-07-19T15:00:00.000000Z");

    const [url] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe(
      "/api/admin/metrics/runs/run%2F1?started_at=2026-07-19T15%3A00%3A00.000000Z",
    );
  });

  it("listOnlineEvents encodes kind, experiment_key, and event_name", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ kind: "product", events: [] }), {
        status: 200,
      }),
    );

    await listOnlineEvents({
      kind: "product",
      experimentKey: "exp+1",
      eventName: "proposal_accepted",
      limit: 25,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/metrics/online?kind=product&experiment_key=exp%2B1&event_name=proposal_accepted&limit=25",
      expect.any(Object),
    );
  });
});
