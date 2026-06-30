from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.services.settings import get_tmdb_key

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


# Digital Asset Links — proves the Play Store app and this site belong together,
# so the TWA opens full-screen (no browser URL bar) and passes verification.
# Fingerprints below must match the keys the installed app is signed with.
#  - upload key: from the PWABuilder "Google Play package" (signing-key-info.txt)
#  - Play App Signing key: from Play Console → Setup → App integrity
#    (ADD IT HERE once you copy it from the Console — see notes below)
ASSETLINKS = [
    {
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.onrender.watchwise_kmo5.twa",
            "sha256_cert_fingerprints": [
                # Upload key (PWABuilder)
                "D4:22:72:B8:10:D4:44:6A:CD:54:EF:F4:8D:5D:B1:C1:9D:04:E8:D4:61:39:50:E7:8E:73:C2:43:F9:7A:9F:48",
                # Play App Signing key — paste the SHA-256 from Play Console here:
                # "XX:XX:...",
            ],
        },
    }
]


@router.get("/.well-known/assetlinks.json")
async def assetlinks():
    return JSONResponse(ASSETLINKS)


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
