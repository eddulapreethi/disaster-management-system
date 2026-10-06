from fastapi import HTTPException


def validate_resource_quantity(available: int, requested: int) -> None:
    if requested <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero.")
    if requested > available:
        raise HTTPException(
            status_code=409,
            detail=f"Only {available} units are currently available.",
        )