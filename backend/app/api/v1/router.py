from fastapi import APIRouter
from backend.app.api.v1 import admin, auth, bookings, customers, health, rooms

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(rooms.router)
api_router.include_router(bookings.router)
api_router.include_router(admin.router)
