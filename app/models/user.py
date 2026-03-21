from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime

from app.models.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Integer, default=0)  # 0 = regular, 1 = admin
    created_at = Column(DateTime, default=datetime.utcnow)
