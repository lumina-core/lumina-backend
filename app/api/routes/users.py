from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_users():
    return {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}


@router.get("/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "Alice", "email": "alice@example.com"}


@router.post("")
async def create_user(name: str, email: str):
    return {"id": 3, "name": name, "email": email}
