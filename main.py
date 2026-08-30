import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    STATIC_DIR,
    TEMPLATES_DIR,
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_ADMIN_PASSWORD
)
from app.database import engine, Base, SessionLocal
from app.models import User, ProviderConfig
from app.auth import get_password_hash
from app.services.cleanup_service import sweep_old_files

# Import Routers
from app.routes.pages import router as pages_router
from app.routes.auth_routes import router as auth_router
from app.routes.translation_routes import router as translation_router
from app.routes.payment_routes import router as payment_router
from app.routes.admin_routes import router as admin_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("zirnovisa")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Automatic Database Tables Creation
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)

    # 2. Sweep old temporary files
    sweep_old_files()

    # 3. Seed Default Admin User if table is empty
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()
        if not admin:
            logger.info(f"Creating default admin account ({DEFAULT_ADMIN_EMAIL})...")
            new_admin = User(
                username=DEFAULT_ADMIN_USERNAME,
                email=DEFAULT_ADMIN_EMAIL,
                password_hash=get_password_hash(DEFAULT_ADMIN_PASSWORD),
                is_admin=True
            )
            db.add(new_admin)
            db.commit()

        # Seed sample Mistral provider placeholder if none exists
        count = db.query(ProviderConfig).count()
        if count == 0:
            logger.info("Seeding initial Mistral Provider placeholder...")
            placeholder_config = ProviderConfig(
                provider_name="mistral",
                model_name="mistral-small-latest",
                api_key="your-mistral-api-key-here",
                priority_order=1,
                is_active=False
            )
            db.add(placeholder_config)
            db.commit()
    finally:
        db.close()

    logger.info("ZirNovisa server started successfully.")
    yield
    logger.info("ZirNovisa server shutting down...")

app = FastAPI(
    title="ZirNovisa | ترجمه زیرنویس با هوش مصنوعی",
    description="سرویس تک‌سرویس و مدرن ترجمه آنلاین فایل‌های زیرنویس SRT با هوش مصنوعی و FastAPI",
    version="1.0.0",
    lifespan=lifespan
)

# Mount Static Assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Register Routers
app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(translation_router)
app.include_router(payment_router)
app.include_router(admin_router)

# Custom 404 Handler
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return templates.TemplateResponse(
        request=request,
        name="components/error_card.html",
        context={"error": "صفحه یا منبع درخواستی یافت نشد (404)."},
        status_code=404
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
