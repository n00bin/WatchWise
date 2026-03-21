from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False)  # "issue" or "feature"
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="open")  # open, in_progress, done, closed
    created_at = Column(DateTime, default=datetime.utcnow)

    votes = relationship("FeedbackVote", backref="feedback", cascade="all, delete-orphan")


class FeedbackVote(Base):
    __tablename__ = "feedback_votes"
    __table_args__ = (
        UniqueConstraint("feedback_id", "user_id", name="uq_vote_user_feedback"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    feedback_id = Column(Integer, ForeignKey("feedback.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
