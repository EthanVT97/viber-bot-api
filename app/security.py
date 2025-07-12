from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from config import config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

async def validate_api_key(api_key: str = Depends(api_key_header)):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    if api_key not in [config.CUSTOMER_API_KEY, config.BILLING_API_KEY, config.CHATLOG_API_KEY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    return api_key

async def validate_admin_token(token: str = Depends(oauth2_scheme)):
    if token != config.ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication credentials"
        )
    return token
