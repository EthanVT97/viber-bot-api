from pydantic import BaseSettings, AnyUrl, IPvAnyAddress, PostgresDsn, RedisDsn, SecretStr
from typing import Optional, Literal
from dotenv import load_dotenv
import logging

# Load .env file before settings initialization
load_dotenv()

class AppSettings(BaseSettings):
    # Database Configuration
    DATABASE_URL: PostgresDsn = "postgres://user:pass@localhost:5432/viberbot"
    DATABASE_POOL_MIN: int = 2
    DATABASE_POOL_MAX: int = 10
    DATABASE_TIMEOUT: int = 30
    
    # Redis Configuration
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20
    
    # API Security
    CUSTOMER_API_KEY: SecretStr
    BILLING_API_KEY: SecretStr
    CHATLOG_API_KEY: SecretStr
    ADMIN_SECRET: SecretStr
    
    # Network Security
    WHITELISTED_IP: IPvAnyAddress = "127.0.0.1"
    CORS_ORIGINS: list[str] = ["*"]
    
    # Monitoring & Observability
    SENTRY_DSN: Optional[AnyUrl] = None
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    
    # Application Environment
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    
    # Rate Limiting
    RATE_LIMIT: int = 100
    RATE_LIMIT_PERIOD: int = 60  # in seconds
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        secrets_dir = "/run/secrets"  # For Docker secrets
        
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ):
            # Priority: env vars > .env file > secrets files > defaults
            return (
                init_settings,
                env_settings,
                file_secret_settings,
            )

# Initialize settings
try:
    settings = AppSettings()
except Exception as e:
    logging.error(f"Failed to load configuration: {e}")
    raise

# Configure logging immediately
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Helper functions for specific config groups
def get_database_config():
    return {
        "url": settings.DATABASE_URL,
        "min_size": settings.DATABASE_POOL_MIN,
        "max_size": settings.DATABASE_POOL_MAX,
        "timeout": settings.DATABASE_TIMEOUT
    }

def get_redis_config():
    return {
        "url": settings.REDIS_URL,
        "max_connections": settings.REDIS_MAX_CONNECTIONS,
        "encoding": "utf-8",
        "decode_responses": True
    }

def get_security_config():
    return {
        "customer_key": settings.CUSTOMER_API_KEY.get_secret_value(),
        "billing_key": settings.BILLING_API_KEY.get_secret_value(),
        "chatlog_key": settings.CHATLOG_API_KEY.get_secret_value(),
        "admin_secret": settings.ADMIN_SECRET.get_secret_value(),
        "whitelisted_ip": settings.WHITELISTED_IP
    }
