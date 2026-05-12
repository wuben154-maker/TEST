import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock api-client before importing the module under test
vi.mock("@/lib/api-client", () => ({
  getAuthToken: () => "test-token",
}));

vi.mock("@/lib/config", () => ({
  activeApiBaseUrl: "http://localhost:8000",
}));

describe("loggerRemoteSink", () => {
  let createRemoteSink: typeof import("./loggerRemoteSink").createRemoteSink;
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.useFakeTimers();
    fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchSpy);
    vi.stubGlobal("navigator", { onLine: true });

    vi.resetModules();
    const mod = await import("./loggerRemoteSink");
    createRemoteSink = mod.createRemoteSink;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("only forwards warn and error entries", () => {
    const sink = createRemoteSink({ batchSize: 1 });

    sink({ timestamp: "t", level: "debug", event: "a" });
    sink({ timestamp: "t", level: "info", event: "b" });
    expect(fetchSpy).not.toHaveBeenCalled();

    sink({ timestamp: "t", level: "warn", event: "c" });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("batches entries up to batchSize then flushes", () => {
    const sink = createRemoteSink({ batchSize: 3 });

    sink({ timestamp: "t", level: "error", event: "e1" });
    sink({ timestamp: "t", level: "error", event: "e2" });
    expect(fetchSpy).not.toHaveBeenCalled();

    sink({ timestamp: "t", level: "error", event: "e3" });
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.errors).toHaveLength(3);
    expect(body.errors[0].event).toBe("e1");
  });

  it("flushes on timer interval", async () => {
    const sink = createRemoteSink({ batchSize: 100, flushIntervalMs: 5000 });

    sink({ timestamp: "t", level: "error", event: "e1" });
    expect(fetchSpy).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("handles network failure without crashing", async () => {
    fetchSpy.mockRejectedValue(new TypeError("Failed to fetch"));
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    const sink = createRemoteSink({ batchSize: 1, maxRetries: 0 });

    expect(() => {
      sink({ timestamp: "t", level: "error", event: "e1" });
    }).not.toThrow();

    // Let promise settle
    await vi.advanceTimersByTimeAsync(100);

    warnSpy.mockRestore();
  });

  it("skips POST when navigator.onLine is false", () => {
    vi.stubGlobal("navigator", { onLine: false });
    const sink = createRemoteSink({ batchSize: 1 });

    sink({ timestamp: "t", level: "error", event: "e1" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("includes auth token in headers", () => {
    const sink = createRemoteSink({ batchSize: 1 });
    sink({ timestamp: "t", level: "error", event: "e1" });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const headers = fetchSpy.mock.calls[0][1].headers;
    expect(headers["Authorization"]).toBe("Bearer test-token");
  });

  it("sends extra fields in the extra object", () => {
    const sink = createRemoteSink({ batchSize: 1 });
    sink({
      timestamp: "t",
      level: "error",
      event: "e1",
      request_id: "abc",
      url: "/api/foo",
    });

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.errors[0].extra.request_id).toBe("abc");
    expect(body.errors[0].extra.url).toBe("/api/foo");
  });
});
