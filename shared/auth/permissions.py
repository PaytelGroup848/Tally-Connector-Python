"""
CtrlBooks - Permission Machine-Readable Codes & Definitions
-----------------------------------------------------------------------
Centralized definitions for granular system permissions across all modules.
"""

class Permissions:
    USERS_VIEW = "users.view"
    USERS_CREATE = "users.create"
    USERS_UPDATE = "users.update"
    USERS_DELETE = "users.delete"

    ROLES_VIEW = "roles.view"
    ROLES_CREATE = "roles.create"
    ROLES_UPDATE = "roles.update"
    ROLES_DELETE = "roles.delete"

    CONNECTORS_VIEW = "connectors.view"
    CONNECTORS_CREATE = "connectors.create"
    CONNECTORS_UPDATE = "connectors.update"
    CONNECTORS_DELETE = "connectors.delete"
    CONNECTORS_ACTIVATE = "connectors.activate"
    CONNECTORS_DEACTIVATE = "connectors.deactivate"
    CONNECTORS_TEST = "connectors.test"

    TALLY_VIEW = "tally.view"
    TALLY_TEST_CONNECTION = "tally.test_connection"
    TALLY_VIEW_COMPANIES = "tally.view_companies"
    TALLY_SELECT_COMPANY = "tally.select_company"
    TALLY_VIEW_METADATA = "tally.view_metadata"

    METADATA_VIEW = "metadata.view"
    METADATA_DISCOVER = "metadata.discover"
    METADATA_REFRESH = "metadata.refresh"
    METADATA_SEARCH = "metadata.search"
    METADATA_VIEW_SOURCE_DETAILS = "metadata.view_source_details"

    MAPPING_VIEW = "mapping.view"
    MAPPING_CREATE = "mapping.create"
    MAPPING_EDIT = "mapping.edit"
    MAPPING_DELETE = "mapping.delete"
    MAPPING_VALIDATE = "mapping.validate"
    MAPPING_PREVIEW = "mapping.preview"
    MAPPING_ACTIVATE = "mapping.activate"
    MAPPING_DEACTIVATE = "mapping.deactivate"

    DATA_EXTRACT = "data.extract"
    DATA_EXTRACT_PREVIEW = "data.extract.preview"
    DATA_EXTRACT_SINGLE = "data.extract.single"
    DATA_EXTRACTION_HISTORY = "data.extraction.history"

    SYNC_VIEW = "sync.view"
    SYNC_START = "sync.start"
    SYNC_PAUSE = "sync.pause"
    SYNC_CANCEL = "sync.cancel"

    LOGS_VIEW = "logs.view"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_UPDATE = "settings.update"

SYSTEM_PERMISSIONS = [
    (Permissions.USERS_VIEW, "View Users", "View user accounts and profiles", "USERS"),
    (Permissions.USERS_CREATE, "Create User", "Create new user accounts", "USERS"),
    (Permissions.USERS_UPDATE, "Update User", "Edit, activate, deactivate, or reset user passwords", "USERS"),
    (Permissions.USERS_DELETE, "Delete User", "Soft delete or remove user accounts", "USERS"),

    (Permissions.ROLES_VIEW, "View Roles", "View system roles and permission assignments", "ROLES"),
    (Permissions.ROLES_CREATE, "Create Role", "Create custom system roles", "ROLES"),
    (Permissions.ROLES_UPDATE, "Update Role", "Modify role names and permission assignments", "ROLES"),
    (Permissions.ROLES_DELETE, "Delete Role", "Remove custom system roles", "ROLES"),

    (Permissions.CONNECTORS_VIEW, "View Connectors", "View connectors, data sources, and destinations", "CONNECTORS"),
    (Permissions.CONNECTORS_CREATE, "Create Connector", "Create new data connectors and sources", "CONNECTORS"),
    (Permissions.CONNECTORS_UPDATE, "Update Connector", "Modify connector configurations and field mappings", "CONNECTORS"),
    (Permissions.CONNECTORS_DELETE, "Delete Connector", "Delete or archive connector pipelines", "CONNECTORS"),
    (Permissions.CONNECTORS_ACTIVATE, "Activate Connector", "Activate data connector pipelines", "CONNECTORS"),
    (Permissions.CONNECTORS_DEACTIVATE, "Deactivate Connector", "Deactivate active data connector pipelines", "CONNECTORS"),
    (Permissions.CONNECTORS_TEST, "Test Connection", "Execute connection test on data connectors", "CONNECTORS"),

    (Permissions.TALLY_VIEW, "View Tally Integration", "View Tally connector details and parameters", "TALLY"),
    (Permissions.TALLY_TEST_CONNECTION, "Test Tally Connection", "Execute Tally Prime connection tests", "TALLY"),
    (Permissions.TALLY_VIEW_COMPANIES, "View Tally Companies", "Discover open companies from running Tally instance", "TALLY"),
    (Permissions.TALLY_SELECT_COMPANY, "Select Tally Company", "Select and bind target company to Tally pipeline", "TALLY"),
    (Permissions.TALLY_VIEW_METADATA, "View Tally Metadata", "Discover ledgers, groups, voucher types from Tally", "TALLY"),

    (Permissions.METADATA_VIEW, "View Unified Metadata", "Access unified source metadata browser", "METADATA"),
    (Permissions.METADATA_DISCOVER, "Discover Metadata", "Trigger data discovery on connector sources", "METADATA"),
    (Permissions.METADATA_REFRESH, "Refresh Metadata", "Re-discover and reconcile source metadata", "METADATA"),
    (Permissions.METADATA_SEARCH, "Search Metadata", "Search unified source metadata across connectors", "METADATA"),
    (Permissions.METADATA_VIEW_SOURCE_DETAILS, "View Source Attributes", "Inspect raw source-specific metadata attributes", "METADATA"),

    (Permissions.MAPPING_VIEW, "View Mappings", "View mapping definitions and field transformation rules", "MAPPING"),
    (Permissions.MAPPING_CREATE, "Create Mapping", "Create new data mapping definitions", "MAPPING"),
    (Permissions.MAPPING_EDIT, "Edit Mapping", "Modify mapping definitions and field rules", "MAPPING"),
    (Permissions.MAPPING_DELETE, "Delete Mapping", "Archive mapping definitions", "MAPPING"),
    (Permissions.MAPPING_VALIDATE, "Validate Mapping", "Execute schema and transformation validation", "MAPPING"),
    (Permissions.MAPPING_PREVIEW, "Preview Mapping", "Generate transformation preview on sample source records", "MAPPING"),
    (Permissions.MAPPING_ACTIVATE, "Activate Mapping", "Validate and activate data mapping definitions", "MAPPING"),
    (Permissions.MAPPING_DEACTIVATE, "Deactivate Mapping", "Deactivate active mapping definitions", "MAPPING"),

    (Permissions.DATA_EXTRACT, "Extract Source Data", "Read and normalize accounting source data", "EXTRACTION"),
    (Permissions.DATA_EXTRACT_PREVIEW, "Preview Data Extraction", "Execute safe read-only extraction preview", "EXTRACTION"),
    (Permissions.DATA_EXTRACT_SINGLE, "Extract Single Record", "Read single source record by identifier", "EXTRACTION"),
    (Permissions.DATA_EXTRACTION_HISTORY, "View Extraction History", "View data extraction execution history logs", "EXTRACTION"),

    (Permissions.SYNC_VIEW, "View Sync Status", "View sync execution jobs and failure logs", "SYNC"),
    (Permissions.SYNC_START, "Start Sync Job", "Trigger manual sync pipeline execution", "SYNC"),
    (Permissions.SYNC_PAUSE, "Pause Sync Job", "Pause active sync job executions", "SYNC"),
    (Permissions.SYNC_CANCEL, "Cancel Sync Job", "Cancel running sync pipeline jobs", "SYNC"),

    (Permissions.LOGS_VIEW, "View Audit Logs", "Access system activity audit logs and health history", "SYSTEM"),
    (Permissions.SETTINGS_VIEW, "View Settings", "Read global application settings", "SYSTEM"),
    (Permissions.SETTINGS_UPDATE, "Update Settings", "Modify global application settings", "SYSTEM"),
]

ROLE_PERMISSIONS_MAPPING = {
    "ADMIN": [p[0] for p in SYSTEM_PERMISSIONS],
    "OPERATOR": [
        Permissions.USERS_VIEW,
        Permissions.CONNECTORS_VIEW,
        Permissions.CONNECTORS_CREATE,
        Permissions.CONNECTORS_UPDATE,
        Permissions.CONNECTORS_ACTIVATE,
        Permissions.CONNECTORS_DEACTIVATE,
        Permissions.CONNECTORS_TEST,
        Permissions.TALLY_VIEW,
        Permissions.TALLY_TEST_CONNECTION,
        Permissions.TALLY_VIEW_COMPANIES,
        Permissions.TALLY_SELECT_COMPANY,
        Permissions.TALLY_VIEW_METADATA,
        Permissions.METADATA_VIEW,
        Permissions.METADATA_DISCOVER,
        Permissions.METADATA_REFRESH,
        Permissions.METADATA_SEARCH,
        Permissions.METADATA_VIEW_SOURCE_DETAILS,
        Permissions.MAPPING_VIEW,
        Permissions.MAPPING_CREATE,
        Permissions.MAPPING_EDIT,
        Permissions.MAPPING_VALIDATE,
        Permissions.MAPPING_PREVIEW,
        Permissions.MAPPING_ACTIVATE,
        Permissions.MAPPING_DEACTIVATE,
        Permissions.DATA_EXTRACT,
        Permissions.DATA_EXTRACT_PREVIEW,
        Permissions.DATA_EXTRACT_SINGLE,
        Permissions.DATA_EXTRACTION_HISTORY,
        Permissions.SYNC_VIEW,
        Permissions.SYNC_START,
        Permissions.SYNC_PAUSE,
        Permissions.SYNC_CANCEL,
        Permissions.LOGS_VIEW,
        Permissions.SETTINGS_VIEW,
    ],
    "VIEWER": [
        Permissions.USERS_VIEW,
        Permissions.ROLES_VIEW,
        Permissions.CONNECTORS_VIEW,
        Permissions.TALLY_VIEW,
        Permissions.TALLY_VIEW_COMPANIES,
        Permissions.TALLY_VIEW_METADATA,
        Permissions.METADATA_VIEW,
        Permissions.METADATA_SEARCH,
        Permissions.MAPPING_VIEW,
        Permissions.MAPPING_PREVIEW,
        Permissions.SYNC_VIEW,
        Permissions.LOGS_VIEW,
        Permissions.SETTINGS_VIEW,
    ],
}
