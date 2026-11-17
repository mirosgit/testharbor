from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import check_credentials, clear_session_cookie, require_auth, set_session_cookie
from app.schemas import LoginIn, MeOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=MeOut)
async def login(body: LoginIn, response: Response) -> MeOut:
    if not check_credentials(body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    set_session_cookie(response, body.username)
    return MeOut(principal="admin")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/me", response_model=MeOut)
async def me(principal: Annotated[str, Depends(require_auth)]) -> MeOut:
    return MeOut(principal=principal)
