"""
CtrlBooks - Application Lifecycle Management
--------------------------------------------------------
Provides standardized startup and shutdown sequence orchestration with structured logs.
"""

from typing import Callable, List
from shared.config import get_settings
from shared.logging_config import get_logger
from shared.database import initialize_database

logger = get_logger("app.lifecycle")

class ApplicationLifecycle:
    """Manages clean startup and shutdown sequences for application components."""
    def __init__(self, service_name: str = "app"):
        self.service_name = service_name
        self.startup_hooks: List[Callable[[], None]] = []
        self.shutdown_hooks: List[Callable[[], None]] = []
        self.is_ready: bool = False

    def add_startup_hook(self, hook: Callable[[], None]) -> None:
        self.startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: Callable[[], None]) -> None:
        self.shutdown_hooks.append(hook)

    def startup(self) -> None:
        """Executes startup sequence with meaningful logs."""
        logger.info(f"[{self.service_name}] Application starting")

        settings = get_settings()
        logger.info(f"[{self.service_name}] Environment loaded: {settings.app_environment.value}")
        settings.validate_required()
        logger.info(f"[{self.service_name}] Configuration validated (Debug={settings.debug})")

        logger.info(f"[{self.service_name}] Initializing core database & storage services")
        initialize_database()

        for hook in self.startup_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"[{self.service_name}] Error executing startup hook {hook.__name__}: {e}")
                raise

        self.is_ready = True
        logger.info(f"[{self.service_name}] Application ready")

    def shutdown(self) -> None:
        """Executes shutdown sequence releasing resources."""
        logger.info(f"[{self.service_name}] Application shutting down")
        self.is_ready = False

        for hook in reversed(self.shutdown_hooks):
            try:
                hook()
            except Exception as e:
                logger.error(f"[{self.service_name}] Error executing shutdown hook {hook.__name__}: {e}")

        logger.info(f"[{self.service_name}] Application stopped cleanly")
