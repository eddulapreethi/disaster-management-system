from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.user import User
from app.services.geocoding_service import search_locations
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/geocoding", tags=["geocoding"])


@router.get("/search")
def geocode_search(
    query: str = Query(..., min_length=2, description="Place name or administrative area to search"),
    limit: int = Query(8, ge=1, le=10),
    _user: User = Depends(get_current_user),
):
    try:
        results = search_locations(query, limit=limit)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return {
        "query": query,
        "provider": "open-meteo-geocoding",
        "count": len(results),
        "results": results,
    }
