from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_products():
    return {"products": [{"id": 1, "name": "Laptop"}, {"id": 2, "name": "Phone"}]}


@router.get("/{product_id}")
async def get_product(product_id: int):
    return {"id": product_id, "name": "Laptop", "price": 999.99}


@router.get("/{product_id}/reviews")
async def get_product_reviews(product_id: int):
    return {"product_id": product_id, "reviews": [{"rating": 5, "comment": "Great!"}]}
