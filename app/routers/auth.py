from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth")


@router.post("/register")
async def register(data: dict, db: Session = Depends(get_db)):
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="Username, email, and password required")

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already taken")

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.username)
    return {
        "user_id": user.id,
        "username": user.username,
        "access_token": token,
    }


@router.post("/login")
async def login(data: dict, response: Response, db: Session = Depends(get_db)):
    login_id = data.get("email", "").strip().lower() or data.get("username", "").strip()
    password = data.get("password", "")

    if not login_id or not password:
        raise HTTPException(status_code=400, detail="Email/username and password required")

    user = (
        db.query(User)
        .filter((User.email == login_id) | (User.username == login_id))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.id, user.username)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="lax",
    )
    return {
        "user_id": user.id,
        "username": user.username,
        "access_token": token,
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"status": "ok"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


@router.post("/change-password")
async def change_password(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    password = data.get("password", "")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.password_hash = hash_password(password)
    db.commit()
    return {"status": "ok"}


@router.delete("/delete-account")
async def delete_account(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.media import Movie, TVShow, Anime

    # Delete all user data
    db.query(Movie).filter(Movie.user_id == user.id).delete()
    db.query(TVShow).filter(TVShow.user_id == user.id).delete()
    db.query(Anime).filter(Anime.user_id == user.id).delete()
    db.delete(user)
    db.commit()

    response.delete_cookie("access_token")
    return {"status": "ok"}
