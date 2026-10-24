from fastapi import APIRouter

from . import auth, dashboard, machines, online, rooms, tickets, users

router = APIRouter(prefix="/api/v1")
for module in (auth, dashboard, machines, online, rooms, tickets, users):
    router.include_router(module.router)
