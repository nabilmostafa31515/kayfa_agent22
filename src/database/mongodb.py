"""MongoDB Atlas connection manager."""

import os
import logging
from pymongo import MongoClient
from pymongo.database import Database
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("MONGODB_URI not set in environment")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        logger.info("MongoDB client created")
    return _client


def get_db() -> Database:
    db_name = os.getenv("MONGODB_DB", "kayfa_crm")
    return get_client()[db_name]


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception as e:
        logger.error(f"MongoDB ping failed: {e}")
        return False
