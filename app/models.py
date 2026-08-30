from datetime import datetime, date
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    subscription_end_date = Column(DateTime, nullable=True)
    daily_usage = Column(Integer, default=0, nullable=False)
    last_usage_date = Column(Date, default=date.today, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tasks = relationship("TranslationTask", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_vip(self) -> bool:
        if self.subscription_end_date:
            return self.subscription_end_date > datetime.utcnow()
        return False

    @property
    def remaining_vip_days(self) -> int:
        if self.is_vip and self.subscription_end_date:
            delta = self.subscription_end_date - datetime.utcnow()
            return max(0, delta.days + 1)
        return 0

    @property
    def max_daily_quota(self) -> int:
        return 10 if self.is_vip else 3

    def check_and_reset_daily_usage(self):
        today = date.today()
        if self.last_usage_date != today:
            self.daily_usage = 0
            self.last_usage_date = today


class GuestUsage(Base):
    __tablename__ = "guest_usages"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(100), unique=True, index=True, nullable=False)  # IP or guest UUID
    daily_usage = Column(Integer, default=0, nullable=False)
    last_usage_date = Column(Date, default=date.today, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def check_and_reset_daily_usage(self):
        today = date.today()
        if self.last_usage_date != today:
            self.daily_usage = 0
            self.last_usage_date = today


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(50), default="mistral", nullable=False)
    model_name = Column(String(100), default="mistral-small-latest", nullable=False)
    api_key = Column(String(255), nullable=False)
    priority_order = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TranslationTask(Base):
    __tablename__ = "translation_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    original_filename = Column(String(255), nullable=False)
    translated_filename = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=True)
    translated_file_path = Column(String(500), nullable=True)
    target_lang = Column(String(20), default="fa", nullable=False)
    status = Column(String(30), default="pending", nullable=False)  # pending, processing, completed, failed
    progress = Column(Integer, default=0, nullable=False)  # 0 to 100
    current_step = Column(String(255), default="در صف پردازش", nullable=False)
    char_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="tasks")


class EmailOTP(Base):
    __tablename__ = "email_otps"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), index=True, nullable=False)
    username = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    otp_code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
