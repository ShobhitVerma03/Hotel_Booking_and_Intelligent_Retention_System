import { expect, test } from "vitest";
test("manager API client exports request", async () => expect(typeof (await import("./client.js")).request).toBe("function"));
