from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import unauthorized
from app.db.session import get_session
from app.modules.auth.service import AuthService, CurrentUser

# auto_error=False so missing credentials use the shared 401 envelope.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token from /auth/login.")

Session = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(request: Request, session: Session) -> AuthService:
    state = request.app.state
    return AuthService(session, state.settings, state.passwords, state.tokens, state.reset_delivery)


Auth = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    auth: Auth,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    """Verified, unrevoked session of an active user. Owner identity comes only from here."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    return await auth.authenticate(credentials.credentials)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
