import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthContext, Book, BookingDetail, Bookings, FormAuth, Protected, Retention, Rooms } from "./main";

const session = { token: "customer-token", user: { role: "customer", customer_id: 9 } };
const withAuth = (ui) => <MemoryRouter><AuthContext.Provider value={{ session, save: vi.fn(), logout: vi.fn() }}>{ui}</AuthContext.Provider></MemoryRouter>;
beforeEach(() => { global.fetch = vi.fn(); localStorage.clear(); });

test("login submits customer credentials", async () => {
  const save = vi.fn();
  global.fetch.mockResolvedValue({ ok: true, json: async () => ({ access_token: "t", user: { role: "customer", customer_id: 9 } }) });
  render(<MemoryRouter><AuthContext.Provider value={{ session: null, save, logout: vi.fn() }}><FormAuth /></AuthContext.Provider></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "guest@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password1" } });
  fireEvent.submit(screen.getByRole("button", { name: "Login" }).closest("form"));
  await waitFor(() => expect(save).toHaveBeenCalled());
});

test("protected route redirects without a customer session", () => {
  render(<MemoryRouter initialEntries={["/private"]}><AuthContext.Provider value={{ session: null, save: vi.fn(), logout: vi.fn() }}><Routes><Route path="/private" element={<Protected><p>private</p></Protected>} /><Route path="/login" element={<p>login page</p>} /></Routes></AuthContext.Provider></MemoryRouter>);
  expect(screen.getByText("login page")).toBeTruthy();
});

test("rooms load and booking uses authenticated customer ID", async () => {
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => [{ room_id: 3, room_type: "Deluxe", room_number: "301", capacity: 2, price_per_night: 4200 }] });
  const view = render(withAuth(<Rooms />));
  await screen.findByText("Room 301");
  view.unmount();
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ booking_id: 51, status: "confirmed", welcome_offer: null }) });
  render(withAuth(<Book />));
  fireEvent.change(screen.getByLabelText("Room ID"), { target: { value: "3" } });
  fireEvent.change(screen.getByLabelText("Check in"), { target: { value: "2027-01-10" } });
  fireEvent.change(screen.getByLabelText("Check out"), { target: { value: "2027-01-12" } });
  fireEvent.submit(screen.getByRole("button", { name: "Confirm booking" }).closest("form"));
  await screen.findByText("Booking confirmed");
  expect(global.fetch.mock.calls[1][1].body).toContain('"customer_id":9');
});

test("booking history and retention status render backend responses", async () => {
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => [{ booking_id: 5, room_type: "Deluxe", room_number: "301", check_in: "2027-01-10", check_out: "2027-01-12", status: "confirmed", booking_amount: 8400 }] });
  const view = render(withAuth(<Bookings />));
  await screen.findByText("₹8400");
  view.unmount();
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ request_id: 6, status: "offered", offer: { description: "Policy-approved rate", discount: 10, offer_type: "discount" } }) });
  render(<MemoryRouter initialEntries={["/retention/6"]}><AuthContext.Provider value={{ session, save: vi.fn(), logout: vi.fn() }}><Routes><Route path="/retention/:requestId" element={<Retention />} /></Routes></AuthContext.Provider></MemoryRouter>);
  await screen.findByText("Policy-approved rate");
  expect(screen.getByText(/available in a later phase/i)).toBeTruthy();
});

test("cancellation is submitted only after explicit confirmation", async () => {
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ booking_id: 5, room_type: "Deluxe", room_number: "301", check_in: "2027-01-10", check_out: "2027-01-12", guests: 2, final_amount: 8400, status: "confirmed" }) });
  render(<MemoryRouter initialEntries={["/bookings/5"]}><AuthContext.Provider value={{ session, save: vi.fn(), logout: vi.fn() }}><Routes><Route path="/bookings/:id" element={<BookingDetail />} /></Routes></AuthContext.Provider></MemoryRouter>);
  await screen.findByText("Booking #5");
  fireEvent.click(screen.getByRole("button", { name: "Cancel booking" }));
  expect(screen.getByRole("button", { name: "Confirm cancellation" })).toBeTruthy();
  expect(global.fetch).toHaveBeenCalledTimes(1);
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ request_id: 77, status: "pending" }) });
  fireEvent.change(screen.getByLabelText("Cancellation reason"), { target: { value: "Plans changed" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm cancellation" }));
  await screen.findByText(/Cancellation request #77 was submitted/i);
  expect(global.fetch).toHaveBeenCalledTimes(2);
});
