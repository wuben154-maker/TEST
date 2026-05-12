"""API routers package."""

from app.api.account_api import router as account_router
from app.api.auth import router as auth_router
from app.api.billing_api import router as billing_router
from app.api.client_errors import router as client_errors_router
from app.api.projects import router as projects_router
from app.api.messages import router as messages_router
from app.api.shared_reports import router as shared_reports_router
from app.api.uploads import router as uploads_router
from app.api.knowledge import router as knowledge_router

__all__ = [
    "account_router",
    "auth_router",
    "billing_router",
    "client_errors_router",
    "projects_router",
    "messages_router",
    "shared_reports_router",
    "uploads_router",
    "knowledge_router",
]
