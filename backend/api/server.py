"""
SAFARI API Server — FastAPI app deployed as Modal ASGI function.

Deployment:
    modal deploy backend/api/server.py

Endpoints:
    POST /api/v1/infer/{model_slug}       — Sync image inference
    POST /api/v1/infer/{model_slug}/video — Async video (returns job_id)
    GET  /api/v1/jobs/{job_id}            — Poll job status/progress
    GET  /health                          — Health check

Authentication:
    All /api/v1/* endpoints require: Authorization: Bearer safari_xxxxx...
"""

from pathlib import Path

import modal

# Modal app configuration
app = modal.App("safari-api-inference")

# Get the project root (parent of backend/)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Build image with dependencies and local backend code
# Version: 5 - sam3_confidence column rename
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.109.0",
        "uvicorn>=0.27.0",
        "pydantic>=2.0.0",
        "supabase>=2.0.0",
        "python-multipart>=0.0.6",  # Required for file uploads
    )
    # Add the backend directory to the container (copy=True bakes into image)
    .add_local_dir(
        str(PROJECT_ROOT / "backend"),
        remote_path="/root/backend",
        copy=True,  # Bake into image for reliable updates
    )
)


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("supabase-credentials"),
    ],
    scaledown_window=300,   # Keep warm for 5 minutes
)
@modal.concurrent(max_inputs=100)  # Handle multiple requests per container
@modal.asgi_app()
def serve():
    """
    Modal ASGI entrypoint — serves the FastAPI app.
    
    All imports happen inside this function so they're resolved
    in the Modal container where dependencies are installed.
    """
    import sys
    # Add /root to path so 'backend' package is importable
    sys.path.insert(0, "/root")
    
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    # Create FastAPI app
    fastapi_app = FastAPI(
        title="SAFARI Inference API",
        description="Public REST API for wildlife detection model inference",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # CORS configuration
    # In production, restrict origins to known clients
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:8000",
            "https://safari.app",
            "https://*.safari.app",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Import and register routes
    from backend.api.routes.inference import router as inference_router
    from backend.api.routes.jobs import router as jobs_router
    
    fastapi_app.include_router(inference_router)
    fastapi_app.include_router(jobs_router)
    
    # Health check endpoint (no auth required)
    @fastapi_app.get("/health", tags=["system"])
    async def health_check():
        """Health check endpoint for load balancers and monitoring."""
        return {"status": "healthy", "service": "safari-api"}
    
    # Root endpoint with API info
    @fastapi_app.get("/", tags=["system"])
    async def root():
        """API information and documentation links."""
        return {
            "name": "SAFARI Inference API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
        }
    
    return fastapi_app


# Local development mode
if __name__ == "__main__":
    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        print("Starting SAFARI API in local development mode...")
        print("Note: Make sure SUPABASE_URL and SUPABASE_KEY are set in .env")
        print("Docs available at: http://localhost:8080/docs")
        
        # For local dev, we need to create the app inline
        # since the routes use relative imports that work in Modal
        app_local = FastAPI(
            title="SAFARI Inference API (Local)",
            version="1.0.0",
        )
        
        @app_local.get("/health")
        async def health():
            return {"status": "healthy", "service": "safari-api-local"}
        
        @app_local.get("/")
        async def root():
            return {"message": "SAFARI API - Local Dev Mode", "docs": "/docs"}
        
        uvicorn.run(app_local, host="0.0.0.0", port=8080)
        
    except ImportError as e:
        print(f"Missing dependency for local dev: {e}")
        print("Install with: pip install fastapi uvicorn")
