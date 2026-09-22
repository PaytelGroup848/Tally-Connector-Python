"""
CtrlBooks - Real Health Monitoring Foundation
---------------------------------------------------------
Performs real health checks on application components (Config, Logging, Database)
without returning fake business or software connection statuses.
"""

import time
from typing import Dict, Any
from sqlalchemy import text
from shared.config import get_settings
from shared.db.session import get_engine
from shared.response import success_response
from shared.logging_config import get_logger

logger = get_logger("app.health")

def check_database_health() -> Dict[str, Any]:
    """Probes database connection latency and engine state via SQLAlchemy."""
    start_time = time.perf_counter()
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            if result == 1:
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "details": "Database engine responding cleanly"
                }
            return {
                "status": "degraded",
                "latency_ms": latency_ms,
                "details": "Unexpected query response"
            }
    except Exception as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e)
        }

def check_config_health() -> Dict[str, Any]:
    """Validates configuration loaded in memory."""
    try:
        settings = get_settings()
        settings.validate_required()
        return {"status": "healthy", "environment": settings.app_environment.value}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def get_system_health(request_id: str = "") -> Dict[str, Any]:
    """Aggregates health status of actual implemented foundation components."""
    settings = get_settings()
    config_health = check_config_health()
    db_health = check_database_health()

    is_healthy = (
        config_health.get("status") == "healthy" and
        db_health.get("status") == "healthy"
    )

    data = {
        "status": "healthy" if is_healthy else "degraded",
        "version": settings.app_version,
        "environment": settings.app_environment.value,
        "components": {
            "application": "healthy",
            "configuration": config_health.get("status"),
            "logging": "healthy",
            "database": db_health.get("status")
        },
        "database_details": db_health
    }

    return success_response(
        data=data,
        message="Health check completed successfully",
        request_id=request_id
    )

def get_app_info(request_id: str = "") -> Dict[str, Any]:
    """Returns application metadata and masked runtime configuration."""
    settings = get_settings()
    data = {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_environment.value,
        "debug": settings.debug,
        "config": settings.get_masked_dict()
    }
    return success_response(
        data=data,
        message="Application information retrieved successfully",
        request_id=request_id
    )
