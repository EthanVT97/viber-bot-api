from slowapi import Limiter
from slowapi.util import get_remote_address
from config import config

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour", "10 per minute"]
)

def get_rate_limiter():
    return limiter
