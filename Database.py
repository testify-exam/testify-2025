from sqlalchemy import (
    Column, Integer, String, Boolean, Text, ForeignKey, DateTime, CheckConstraint
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from typing import AsyncGenerator
import os
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///app.db"  
)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all) 
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully!")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(Text, nullable=False)
    password_hash = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    approved = Column(Integer, default=0)
    is_team_lead = Column(Integer, default=0)
    roll_number = Column(Text)
    register_number = Column(Text)
    department_id = Column(Integer, ForeignKey("departments.id"))
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            role.in_(["teacher", "student", "admin"]),
            name="users_role_check"
        ),
    )

    department = relationship("Department", back_populates="users")
    exams = relationship("Exam", back_populates="teacher")
    feedbacks = relationship("Feedback", back_populates="user")
    exam_attempts = relationship("ExamAttempt", back_populates="student")


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    users = relationship("User", back_populates="department")
    exams = relationship("Exam", back_populates="department")


class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(Text, nullable=False)
    subject = Column(Text, nullable=False)
    start_time = Column(DateTime(timezone=False), nullable=False)
    end_time = Column(DateTime(timezone=False), nullable=False)
    duration = Column(Integer, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    teacher = relationship("User", back_populates="exams")
    department = relationship("Department", back_populates="exams")
    questions = relationship(
        "Question",
        back_populates="exam",
        cascade="all, delete-orphan",   
        passive_deletes=True
    )
    attempts = relationship(
        "ExamAttempt",
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    exam = relationship("Exam", back_populates="questions")
    options = relationship(
        "Option",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    responses = relationship(
        "ExamResponse",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


class Option(Base):
    __tablename__ = "options"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    option_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)

    question = relationship("Question", back_populates="options")


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_time = Column(DateTime(timezone=False), server_default=func.now())
    end_time = Column(DateTime(timezone=False))
    score = Column(Integer)
    status = Column(Text, default="pending")
    is_score_public = Column(Boolean, default=True)

    exam = relationship("Exam", back_populates="attempts")
    student = relationship("User", back_populates="exam_attempts")
    responses = relationship("ExamResponse", back_populates="exam_attempt")


class ExamResponse(Base):
    __tablename__ = "exam_responses"
    id = Column(Integer, primary_key=True)
    exam_attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option_id = Column(Integer, ForeignKey("options.id"))

    exam_attempt = relationship("ExamAttempt", back_populates="responses")
    question = relationship("Question", back_populates="responses")
    selected_option = relationship("Option")


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "(rating >= 1 AND rating <= 5)",
            name="feedback_rating_check"
        ),
    )

    user = relationship("User", back_populates="feedbacks")
    replies = relationship("FeedbackReply", back_populates="feedback")


class FeedbackReply(Base):
    __tablename__ = "feedback_replies"
    id = Column(Integer, primary_key=True)
    feedback_id = Column(Integer, ForeignKey("feedback.id"), nullable=False)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reply_message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    feedback = relationship("Feedback", back_populates="replies")
    admin = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    recipients = relationship("NotificationRecipient", back_populates="notification")
    sender = relationship("User")


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"
    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_read = Column(Boolean, default=False)

    notification = relationship("Notification", back_populates="recipients")
    recipient = relationship("User")
