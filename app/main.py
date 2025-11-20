from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pathlib import Path
import os
from app.config import settings
from app.database import engine, Base
from app.api import auth, templates, generation, admin, test, payment , test_payment
import app.models
import logging

logger = logging.getLogger(__name__)
Base.metadata.create_all(bind=engine)

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.GENERATED_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.TEMPLATE_PREVIEW_DIR).mkdir(parents=True, exist_ok=True)  # New directory

Path("app/templates").mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Wedding Image Generator API",
    description="Pre-wedding image generation service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/generated", StaticFiles(directory=settings.GENERATED_DIR), name="generated")
app.mount("/template_previews", StaticFiles(directory=settings.TEMPLATE_PREVIEW_DIR), name="template_previews")

app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(generation.router)
app.include_router(admin.router)
app.include_router(payment.router)
app.include_router(test.router)
app.include_router(test_payment.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "message": "An unexpected error occurred",
            "detail": str(exc)
        }
    )

@app.get("/")
async def root():
    return {
        "message": "Wedding Image Generator API",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected"
    }
    
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    directories = [
        settings.UPLOAD_DIR,
        settings.GENERATED_DIR,
        settings.TEMPLATE_PREVIEW_DIR
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        logger.info(f"Directory ready: {directory}")
    
    logger.info("🚀 Application started successfully")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)