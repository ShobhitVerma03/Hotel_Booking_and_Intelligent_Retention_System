import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Analytics, AuthContext, Dashboard, Login, Protected } from "./main";

const manager = { token: "manager-token", user: { role: "manager", id: 1 } };
const withManager = (ui) => <MemoryRouter><AuthContext.Provider value={{ session: manager, save: vi.fn(), logout: vi.fn() }}>{ui}</AuthContext.Provider></MemoryRouter>;
beforeEach(() => { global.fetch = vi.fn(); localStorage.clear(); });

test("manager login saves a manager session", async () => {
  const save = vi.fn();
  global.fetch.mockResolvedValue({ ok: true, json: async () => ({ access_token: "m", user: { role: "manager", id: 1 } }) });
  render(<MemoryRouter><AuthContext.Provider value={{ session: null, save, logout: vi.fn() }}><Login /></AuthContext.Provider></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "manager@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password1" } });
  fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form"));
  await waitFor(() => expect(save).toHaveBeenCalled());
});

test("manager routes reject customer sessions", () => {
  render(<MemoryRouter initialEntries={["/secure"]}><AuthContext.Provider value={{ session: { user: { role: "customer" } }, save: vi.fn(), logout: vi.fn() }}><Routes><Route path="/secure" element={<Protected><p>admin</p></Protected>} /><Route path="/login" element={<p>manager login</p>} /></Routes></AuthContext.Provider></MemoryRouter>);
  expect(screen.getByText("manager login")).toBeTruthy();
});

test("dashboard renders API-derived metrics", async () => {
  global.fetch.mockResolvedValue({ ok: true, json: async () => ({ customers: { total: 4 }, bookings: { active: 3 } }) });
  render(withManager(<Dashboard />));
  await screen.findByText("customers · total");
  expect(screen.getByText("3")).toBeTruthy();
});

test("analytics submits a question and displays a secure result", async () => {
  global.fetch.mockResolvedValue({ ok: true, json: async () => ({ language: "hi", intent: "booking count", sql: "SELECT COUNT(*) AS total FROM bookings LIMIT 100", explanation: "Count", row_count: 1, columns: ["total"], rows: [{ total: 7 }] }) });
  render(withManager(<Analytics />));
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "मुंबई से कितनी bookings हुई हैं?" } });
  fireEvent.submit(screen.getByRole("button", { name: "Run secure analysis" }).closest("form"));
  await screen.findByText(/Language: hi/);
  expect(screen.getByText("7")).toBeTruthy();
  expect(screen.getByText(/Tamil is not supported/)).toBeTruthy();
});
