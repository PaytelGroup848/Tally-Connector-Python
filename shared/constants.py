"""
CtrlBooks - System Constants
----------------------------
Central constants for error codes, environment names, and default ports.
"""

from enum import Enum

APP_NAME = "CtrlBooks"
APP_VERSION = "1.0.2"

class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"

class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"

DEFAULT_PORTS = {
    "gateway": 8000,
    "connection": 8001,
    "tally": 8002,
    "normalization": 8004,
    "sync": 8005,
    "change": 8006,
    "storage": 8007,
    "audit": 8008,
    "company": 8009,
}
