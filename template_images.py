"""
Fix template preview_image in RDS using file names
Convert local filenames to S3 URLs
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal
from app.models.template import Template
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_preview_urls():
    db = SessionLocal()

    try:
        templates = db.query(Template).all()
        logger.info(f"Found {len(templates)} templates in DB")

        updated = 0

        for t in templates:
            try:
                # extract filename from current value (local path or filename)
                filename = Path(t.preview_image).name

                # build S3 URL
                s3_url = (
                    f"https://{settings.S3_BUCKET_NAME}.s3.amazonaws.com/"
                    f"template_previews/{filename}"
                )

                old = t.preview_image
                t.preview_image = s3_url

                logger.info(f"Template #{t.id} updated")
                logger.info(f"  Old: {old}")
                logger.info(f"  New: {s3_url}")

                updated += 1

            except Exception as e:
                logger.error(f"❌ Failed for template #{t.id}: {e}")

        db.commit()
        logger.info(f"\n✅ Updated {updated} template preview URLs")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    fix_preview_urls()
