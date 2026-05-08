"""AnyLegal OSS — FastAPI entry point.

Default bind is 127.0.0.1 because OSS is single-tenant and unauthenticated.
Set HOST=0.0.0.0 explicitly when running behind a reverse proxy that adds
auth in front of the service, or inside a container managed by docker-compose
(the compose file sets HOST=0.0.0.0 because Docker bridge networking needs it).

Local dev:
    uvicorn main:app --reload --port 8000

Production reverse-proxy:
    HOST=0.0.0.0 uvicorn main:app --port 8000
"""
import os
from anylegal_oss.fastapi_app import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
