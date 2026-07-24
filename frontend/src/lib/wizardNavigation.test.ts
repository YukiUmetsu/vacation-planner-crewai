import { describe, expect, it } from "vitest";
import {
  canNavigateToStep,
  isRouteReadyForDays,
} from "./wizardNavigation";

describe("canNavigateToStep", () => {
  it("allows all steps in demo mode", () => {
    const ctx = {
      demoMode: true,
      hasTrip: false,
      routeReady: false,
      hasDays: false,
    };
    expect(canNavigateToStep("details", ctx)).toBe(true);
    expect(canNavigateToStep("cities", ctx)).toBe(true);
    expect(canNavigateToStep("days", ctx)).toBe(true);
  });

  it("blocks cities/days until a trip exists in live mode", () => {
    const ctx = {
      demoMode: false,
      hasTrip: false,
      routeReady: false,
      hasDays: false,
    };
    expect(canNavigateToStep("details", ctx)).toBe(true);
    expect(canNavigateToStep("cities", ctx)).toBe(false);
    expect(canNavigateToStep("days", ctx)).toBe(false);
  });

  it("allows cities after create; days only when route ready or days exist", () => {
    expect(
      canNavigateToStep("cities", {
        demoMode: false,
        hasTrip: true,
        routeReady: false,
        hasDays: false,
      }),
    ).toBe(true);
    expect(
      canNavigateToStep("days", {
        demoMode: false,
        hasTrip: true,
        routeReady: false,
        hasDays: false,
      }),
    ).toBe(false);
    expect(
      canNavigateToStep("days", {
        demoMode: false,
        hasTrip: true,
        routeReady: true,
        hasDays: false,
      }),
    ).toBe(true);
    expect(
      canNavigateToStep("days", {
        demoMode: false,
        hasTrip: true,
        routeReady: false,
        hasDays: true,
      }),
    ).toBe(true);
  });
});

describe("isRouteReadyForDays", () => {
  it("treats city destinations as ready", () => {
    expect(
      isRouteReadyForDays({
        trip: { status: "draft", destination_type: "city" },
        route: null,
      }),
    ).toBe(true);
  });

  it("requires confirmed route for country trips", () => {
    expect(
      isRouteReadyForDays({
        trip: { status: "proposed", destination_type: "country" },
        route: { status: "proposed" },
      }),
    ).toBe(false);
    expect(
      isRouteReadyForDays({
        trip: { status: "routing_confirmed", destination_type: "country" },
        route: { status: "confirmed" },
      }),
    ).toBe(true);
  });
});
