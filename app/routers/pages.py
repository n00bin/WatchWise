from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.services.settings import get_tmdb_key

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/u/{username}")
async def profile_page(request: Request, username: str):
    return templates.TemplateResponse(request, "profile.html", {
        "page": "profile",
        "username": username,
    })


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"page": "login"})


@router.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {"page": "privacy"})


@router.get("/")
async def dashboard(request: Request):
    has_key = bool(get_tmdb_key())
    return templates.TemplateResponse(request, "dashboard.html", {
        "page": "dashboard",
        "has_api_key": has_key,
    })


@router.get("/movies")
async def movies_page(request: Request):
    return templates.TemplateResponse(request, "movies.html", {"page": "movies"})


@router.get("/tvshows")
async def tvshows_page(request: Request):
    return templates.TemplateResponse(request, "tvshows.html", {"page": "tvshows"})


@router.get("/anime")
async def anime_page(request: Request):
    return templates.TemplateResponse(request, "anime.html", {"page": "anime"})


@router.get("/calendar")
async def calendar_page(request: Request):
    return templates.TemplateResponse(request, "calendar.html", {"page": "calendar"})


@router.get("/recommendations")
async def recommendations_page(request: Request):
    return templates.TemplateResponse(request, "recommendations.html", {"page": "recommendations"})


@router.get("/news")
async def announcements_page(request: Request):
    return templates.TemplateResponse(request, "announcements.html", {"page": "news"})


@router.get("/feedback")
async def feedback_page(request: Request):
    return templates.TemplateResponse(request, "feedback.html", {"page": "feedback"})


@router.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html", {"page": "settings"})
