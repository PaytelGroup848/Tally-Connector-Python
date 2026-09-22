

from typing import Optional
import pymongo
from pymongo.database import Database
from pymongo.collection import Collection
from shared.config import get_settings
from shared.logging_config import get_logger

logger = get_logger("app.db.mongo")

_client: Optional[pymongo.MongoClient] = None
_indexes_initialized: bool = False

def get_mongo_client(uri: Optional[str] = None) -> pymongo.MongoClient:
    """Returns or initializes global thread-safe MongoClient singleton."""
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    connection_uri = uri or settings.effective_mongo_url

    logger.info("Initializing MongoDB Atlas connection client...")
    _client = pymongo.MongoClient(
        connection_uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        maxPoolSize=50,
        minPoolSize=5,
        retryWrites=True,
    )
    return _client

def get_mongo_db(db_name: Optional[str] = None) -> Database:
    """Returns target MongoDB database instance (default: 'test')."""
    client = get_mongo_client()
    settings = get_settings()
    target_db_name = db_name or settings.mongo_db_name or "test"
    db = client[target_db_name]

    ensure_indexes(db)
    return db

def get_collection(name: str) -> Collection:
    """Helper to get a named collection from current database."""
    return get_mongo_db()[name]

def ensure_indexes(db: Database) -> None:
    """Ensures necessary performance and unique indexes on MongoDB collections asynchronously in the background."""
    global _indexes_initialized
    if _indexes_initialized:
        return

    import threading
    def _create_indexes_task():
        global _indexes_initialized
        try:
            db.companies.create_index([("company_name", pymongo.ASCENDING)], background=True)
            db.companies.create_index([("company_guid", pymongo.ASCENDING)], unique=True, sparse=True, background=True)

            db.ledgers.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], unique=True, background=True)
            db.ledgers.create_index([("company_name", pymongo.ASCENDING)], background=True)
            db.ledgers.create_index([("name", pymongo.ASCENDING)], background=True)

            db.customers.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], unique=True, background=True)
            db.customers.create_index([("companyId", pymongo.ASCENDING), ("name", pymongo.ASCENDING)], background=True)
            db.suppliers.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], unique=True, background=True)
            db.suppliers.create_index([("companyId", pymongo.ASCENDING), ("name", pymongo.ASCENDING)], background=True)

            db.vouchers.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], unique=True, background=True)
            db.vouchers.create_index([("company_name", pymongo.ASCENDING), ("date", pymongo.DESCENDING)], background=True)
            db.vouchers.create_index([("companyId", pymongo.ASCENDING), ("date", pymongo.DESCENDING)], background=True)
            db.vouchers.create_index([("partyLedger", pymongo.ASCENDING)], background=True)
            db.sales_invoices.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], background=True)
            db.sales_invoices.create_index([("company_name", pymongo.ASCENDING)], background=True)
            db.purchase_invoices.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], background=True)
            db.purchase_invoices.create_index([("company_name", pymongo.ASCENDING)], background=True)

            db.stock_items.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], background=True)
            db.stock_items.create_index([("company_name", pymongo.ASCENDING), ("name", pymongo.ASCENDING)], background=True)
            db.items.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], unique=True, background=True)
            db.stocks.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], background=True)
            db.stockbalances.create_index([("organizationId", pymongo.ASCENDING), ("companyId", pymongo.ASCENDING), ("tallyExternalId", pymongo.ASCENDING)], unique=True, background=True)

            db.sync_queue.create_index([("status", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)], background=True)
            db.incoming_commands_history.create_index([("organizationId", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)], background=True)
            db.incoming_commands_history.create_index([("user_email", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)], background=True)

            _indexes_initialized = True
            logger.info(f"MongoDB collection indexes verified on database '{db.name}'.")
        except Exception as exc:
            logger.warning(f"Non-fatal MongoDB index setup error: {exc}")

    threading.Thread(target=_create_indexes_task, daemon=True, name="MongoIndexInitializer").start()

def close_mongo_client() -> None:
    """Closes MongoClient and cleans up resources."""
    global _client, _indexes_initialized
    if _client is not None:
        _client.close()
        _client = None
        _indexes_initialized = False
        logger.info("MongoDB client connection closed.")

def serialize_mongo_doc(doc: object) -> object:
    """Recursively converts BSON ObjectIds and non-serializable objects in a document into JSON-serializable primitives."""
    from bson import ObjectId
    if isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    elif isinstance(doc, dict):
        res = {}
        for k, v in doc.items():
            if k == "_id":
                res["id"] = str(v)
            elif isinstance(v, ObjectId):
                res[k] = str(v)
            else:
                res[k] = serialize_mongo_doc(v)
        return res
    elif isinstance(doc, ObjectId):
        return str(doc)
    return doc

