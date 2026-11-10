"""Authentication API endpoints: login, token issuance, and current user info."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response

from app.api.deps import AuthServiceDep, CurrentUserDep
from app.middleware.rate_limit import check_auth_rate_limit
from app.schemas.auth import LoginRequest, TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_token(
    *,
    email: str,
    password: str,
    auth_service: AuthServiceDep,
    response: Response,
    request: Request,
) -> TokenResponse:
    response.headers["Cache-Control"] = "no-store"
    user, token = await auth_service.authenticate(email, password)
    settings = request.app.state.settings
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_ttl_minutes * 60,
        user=UserInfo(id=user.id, email=user.email, role=user.role),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    operation_id="login_user",
    dependencies=[Depends(check_auth_rate_limit)],
)
async def login(
    payload: LoginRequest,
    auth_service: AuthServiceDep,
    response: Response,
    request: Request,
) -> TokenResponse:
    """Authenticate with email and password and receive a JWT access token.

    Demo token endpoint (not a full OAuth 2.0 authorization server).
    """
    return await _issue_token(
        email=payload.email,
        password=payload.password,
        auth_service=auth_service,
        response=response,
        request=request,
    )


@router.post(
    "/token",
    response_model=TokenResponse,
    operation_id="token_login_user",
    include_in_schema=False,
    dependencies=[Depends(check_auth_rate_limit)],
)
async def token(
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    auth_service: AuthServiceDep,
    response: Response,
    request: Request,
) -> TokenResponse:
    """OAuth2 password-flow shaped token endpoint (demo)."""
    return await _issue_token(
        email=username,
        password=password,
        auth_service=auth_service,
        response=response,
        request=request,
    )


@router.get(
    "/me",
    response_model=UserInfo,
    operation_id="get_current_user_info",
)
async def get_current_user_profile(
    current_user: CurrentUserDep,
    response: Response,
) -> UserInfo:
    """Read the profile and role of the currently authenticated user."""
    response.headers["Cache-Control"] = "no-store"
    return UserInfo(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
    )
