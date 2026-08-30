from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username_or_email: str
    password: str

class ProviderConfigCreate(BaseModel):
    provider_name: str = "mistral"
    model_name: str = "mistral-small-latest"
    api_key: str
    priority_order: int = 1
    is_active: bool = True

class ProviderConfigUpdate(BaseModel):
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    priority_order: Optional[int] = None
    is_active: Optional[bool] = None

class TaskStatusResponse(BaseModel):
    id: str
    filename: str
    status: str
    progress: int
    current_step: str
    error_message: Optional[str] = None
    download_url: Optional[str] = None
