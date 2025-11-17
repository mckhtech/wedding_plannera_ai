#!/usr/bin/env python3
"""
Migration script to update Template model
This will drop and recreate the templates table with the new schema
"""

from app.database import engine, Base, SessionLocal
from app.models.template import Template
from sqlalchemy import inspect, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Run migration"""
    logger.info("=" * 60)
    logger.info("DATABASE MIGRATION - Template Model Update")
    logger.info("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Check if templates table exists
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if 'templates' in tables:
            logger.info("   Found existing 'templates' table")
            
            # Check for existing data
            template_count = db.query(Template).count()
            logger.info(f"   Existing templates: {template_count}")
            
            if template_count > 0:
                logger.warning("   ⚠️  WARNING: This will delete all existing templates!")
                response = input("   Continue? (yes/no): ")
                if response.lower() != 'yes':
                    logger.info("   Migration cancelled")
                    return
            
            # Drop the table
            logger.info("   Dropping 'templates' table...")
            Base.metadata.drop_all(bind=engine, tables=[Template.__table__])
            logger.info("   ✅ Table dropped")
        else:
            logger.info("   'templates' table does not exist yet")
        
        # Create the new table
        logger.info("   Creating 'templates' table with new schema...")
        Base.metadata.create_all(bind=engine, tables=[Template.__table__])
        logger.info("   ✅ Table created successfully")
        
        # Verify the new table
        inspector = inspect(engine)
        columns = inspector.get_columns('templates')
        
        logger.info("\n   New table structure:")
        for col in columns:
            logger.info(f"      - {col['name']}: {col['type']}")
        
        # Check for preview_image column
        column_names = [col['name'] for col in columns]
        if 'preview_image' in column_names:
            logger.info("\n   ✅ 'preview_image' column exists (was 'preview_image_url')")
        
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Start your server: python -m app.main")
        logger.info("2. Access admin dashboard: http://localhost:8000/api/admin/dashboard")
        logger.info("3. Login with your admin credentials")
        logger.info("4. Create templates with preview images")
        
    except Exception as e:
        logger.error(f"   ❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()