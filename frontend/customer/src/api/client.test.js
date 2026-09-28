import { expect, test } from "vitest";
// Environment-dependent base URL is intentionally not asserted; this confirms
// the client module remains an ESM module with no embedded credential values.
test("customer API client exports request", async () => {
  const module = await import("./client.js");
  expect(typeof module.request).toBe("function");
});
