import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import AccountCreate, AccountOut, ManualConnectRequest, OAuthAuthorizeResponse
from backend.services import account_service, connection_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    return account_service.list_accounts(db, limit=limit, offset=offset)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    try:
        return account_service.create_account(
            db,
            username=payload.username,
            timezone=payload.timezone,
            daily_min_posts=payload.daily_min_posts,
            daily_max_posts=payload.daily_max_posts,
        )
    except account_service.AccountAlreadyExists as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"account '{exc}' already exists") from exc


@router.get("/oauth/authorize", response_model=OAuthAuthorizeResponse)
def oauth_authorize():
    """
    §9/§17 "Connect Instagram" button: returns the Facebook OAuth dialog
    URL to send the browser to. Requires IG_APP_ID/IG_OAUTH_REDIRECT_URI to
    be configured (a registered Meta Developer App) -- if they aren't,
    responds 501 rather than a broken URL. connect/manual below works
    without any of this.
    """
    try:
        state = connection_service.new_oauth_state()
        return OAuthAuthorizeResponse(authorize_url=connection_service.oauth_authorize_url(state=state), state=state)
    except connection_service.AccountConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc


@router.get("/oauth/callback", response_model=list[AccountOut])
def oauth_callback(code: str, state: str | None = None, db: Session = Depends(get_db)):
    try:
        return connection_service.handle_oauth_callback(db, authorization_code=code)
    except connection_service.AccountConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{account_id}/connect/manual", response_model=AccountOut)
def connect_manual(account_id: uuid.UUID, payload: ManualConnectRequest, db: Session = Depends(get_db)):
    """
    Fallback that works today without Meta App Review: paste a long-lived
    token + Instagram Business Account id obtained via Meta's own Graph API
    Explorer (developers.facebook.com/tools/explorer). Validated against
    the real Graph API before being trusted -- never stored unchecked.
    """
    try:
        return connection_service.connect_manual(
            db, account_id=account_id, ig_business_id=payload.ig_business_id, access_token_plain=payload.access_token
        )
    except connection_service.AccountConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, db: Session = Depends(get_db)):
    # NOTE: must be uuid.UUID, not str -- the underlying column is a native
    # Uuid type and SQLAlchemy's bind processor for it requires an actual
    # uuid.UUID object, not its string form.
    account = account_service.get_account(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    return account
