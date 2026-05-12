import { describe, it, expect, vi, beforeEach } from "vitest";

describe("logger facade", () => {
  // Re-import fresh module for each test to avoid cross-contamination
  let loggerModule: typeof import("./logger");

  beforeEach(async () => {
    vi.resetModules();
    loggerModule = await import("./logger");
  });

  it("exports a logger with debug/info/warn/error methods", () => {
    const { logger } = loggerModule;
    expect(typeof logger.debug).toBe("function");
    expect(typeof logger.info).toBe("function");
    expect(typeof logger.warn).toBe("function");
    expect(typeof logger.error).toBe("function");
  });

  it("supports setLevel to change threshold", () => {
    const { logger } = loggerModule;
    expect(typeof logger.setLevel).toBe("function");
    logger.setLevel("error"); // should not throw
  });

  it("drops events below threshold", () => {
    const { logger } = loggerModule;
    const spy = vi.spyOn(console, "debug").mockImplementation(() => {});
    const infoSpy = vi.spyOn(console, "info").mockImplementation(() => {});

    logger.setLevel("warn");
    logger.debug("should_be_dropped");
    logger.info("also_dropped");

    expect(spy).not.toHaveBeenCalled();
    expect(infoSpy).not.toHaveBeenCalled();

    spy.mockRestore();
    infoSpy.mockRestore();
  });

  it("emits events at or above threshold", () => {
    const { logger } = loggerModule;
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});

    logger.setLevel("warn");
    logger.warn("should_pass");

    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it("outputs structured JSON with timestamp, level, event", () => {
    const { logger } = loggerModule;
    let captured = "";
    vi.spyOn(console, "error").mockImplementation((msg: string) => {
      captured = msg;
    });

    logger.setLevel("error");
    logger.error("test_event", { foo: "bar" });

    const parsed = JSON.parse(captured);
    expect(parsed.level).toBe("error");
    expect(parsed.event).toBe("test_event");
    expect(parsed.foo).toBe("bar");
    expect(parsed.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);

    vi.restoreAllMocks();
  });

  it("addSink receives entries passing the level gate", () => {
    const { logger } = loggerModule;
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const sinkFn = vi.fn();
    logger.addSink(sinkFn);
    logger.setLevel("warn");

    logger.debug("dropped_by_gate");
    expect(sinkFn).not.toHaveBeenCalled();

    logger.warn("passed_gate", { key: "val" });
    expect(sinkFn).toHaveBeenCalledTimes(1);
    expect(sinkFn.mock.calls[0][0].event).toBe("passed_gate");
    expect(sinkFn.mock.calls[0][0].key).toBe("val");

    vi.restoreAllMocks();
  });

  it("handles circular references without throwing", () => {
    const { logger } = loggerModule;
    vi.spyOn(console, "error").mockImplementation(() => {});

    const obj: Record<string, unknown> = { a: 1 };
    obj["self"] = obj;

    expect(() => logger.error("circular_test", obj)).not.toThrow();

    vi.restoreAllMocks();
  });

  it("defaults to debug level in dev mode", () => {
    // import.meta.env.DEV is true in vitest
    const { logger } = loggerModule;
    const spy = vi.spyOn(console, "debug").mockImplementation(() => {});

    logger.debug("dev_debug_visible");
    expect(spy).toHaveBeenCalledTimes(1);

    spy.mockRestore();
  });
});
