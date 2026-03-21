from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services.settings import get_tmdb_key

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


def _has_token(request: Request) -> bool:
    """Check if request has an auth token (cookie or localStorage via JS)."""
    return bool(request.cookies.get("access_token"))


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "page": "login"})


@router.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request, "page": "privacy"})


@router.get("/")
async def dashboard(request: Request):
    has_key = bool(get_tmdb_key())
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "page": "dashboard",
        "has_api_key": has_key,
    })


@router.get("/movies")
async def movies_page(request: Request):
    return templates.TemplateResponse("movies.html", {
        "request": request,
        "page": "movies",
    })


@router.get("/tvshows")
async def tvshows_page(request: Request):
    return templates.TemplateResponse("tvshows.html", {
        "request": request,
        "page": "tvshows",
    })


@router.get("/anime")
async def anime_page(request: Request):
    return templates.TemplateResponse("anime.html", {
        "request": request,
        "page": "anime",
    })


@router.get("/calendar")
async def calendar_page(request: Request):
    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "page": "calendar",
    })


@router.get("/recommendations")
async def recommendations_page(request: Request):
    return templates.TemplateResponse("recommendations.html", {
        "request": request,
        "page": "recommendations",
    })


@router.get("/feedback")
async def feedback_page(request: Request):
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "page": "feedback",
    })


@router.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "page": "settings",
    })
