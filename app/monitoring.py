import sentry_sdk
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI
from config import settings
import logging

def configure_sentry():
    """Configure Sentry SDK with appropriate integrations"""
    if not settings.SENTRY_DSN:
        logging.warning("Sentry DSN not configured - skipping Sentry setup")
        return False

    sentry_logging = LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR
    )

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN.get_secret_value(),
        integrations=[
            FastApiIntegration(),
            RedisIntegration(),
            SqlalchemyIntegration(),
            sentry_logging
        ],
        environment=settings.ENVIRONMENT,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0 if settings.ENVIRONMENT == "production" else 0.1,
        send_default_pii=False,
        debug=settings.DEBUG,
        release=f"viber-bot@{settings.VERSION}" if hasattr(settings, 'VERSION') else None
    )
    return True

def configure_metrics(app: FastAPI):
    """Configure Prometheus metrics collection"""
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="inprogress",
        inprogress_labels=True
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        should_gzip=True
    )

    logging.info("Prometheus metrics configured at /metrics")

def setup_monitoring(app: FastAPI):
    """Main monitoring setup function"""
    # Configure Sentry
    sentry_configured = configure_sentry()
    if sentry_configured:
        app.add_middleware(SentryAsgiMiddleware)
        logging.info("Sentry monitoring configured")

    # Configure Metrics
    if settings.MONITORING_ENABLED:
        configure_metrics(app)
        
    # Health check endpoint
    @app.get("/health", include_in_schema=False)
    async def health_check():
        return {
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
            "monitoring": {
                "sentry": sentry_configured,
                "prometheus": settings.MONITORING_ENABLED
            }
        }
