from sqlalchemy import create_engine, event, pool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from app.config import settings
from sqlalchemy import text

{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::wedplanner/*"
        }
    ]
}
import logging

logger = logging.getLogger(__name__)

# ============================================
# ENGINE CONFIGURATION
# ============================================

engine_kwargs = {
    "poolclass": QueuePool,
    "pool_size": settings.DB_POOL_SIZE,
    "max_overflow": settings.DB_MAX_OVERFLOW,
    "pool_timeout": settings.DB_POOL_TIMEOUT,
    "pool_recycle": settings.DB_POOL_RECYCLE,
    "pool_pre_ping": True,  # Test connections before using
    "echo": settings.DEBUG,  # Log SQL queries in debug mode
}

# Add SSL for PostgreSQL in production
if settings.is_production and "postgresql" in settings.DATABASE_URL:
    engine_kwargs["connect_args"] = {
        "sslmode": "require",
        "connect_timeout": 10
    }

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

# ============================================
# SESSION CONFIGURATION
# ============================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Prevent detached instance errors
)

Base = declarative_base()

# ============================================
# CONNECTION POOL MONITORING
# ============================================

@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log new database connections"""
    logger.debug("New database connection established")

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Monitor connection checkout from pool"""
    logger.debug("Connection checked out from pool")

@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    """Monitor connection return to pool"""
    logger.debug("Connection returned to pool")

# ============================================
# DATABASE DEPENDENCY
# ============================================

def get_db():
    """
    Database session dependency with proper error handling
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

# ============================================
# HEALTH CHECK
# ============================================

def check_db_connection() -> bool:
    """
    Check if database is accessible
    Returns True if healthy, False otherwise
    """
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

def get_pool_status() -> dict:
    """
    Get connection pool statistics
    """
    return {
        "pool_size": engine.pool.size(),
        "checked_in": engine.pool.checkedin(),
        "checked_out": engine.pool.checkedout(),
        "overflow": engine.pool.overflow(),
        "total_connections": engine.pool.size() + engine.pool.overflow()
    }