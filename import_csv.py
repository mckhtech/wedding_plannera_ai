import sys
import csv
from pathlib import Path
from datetime import datetime
import logging

sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal
from app.models.template import Template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_date(date_str):
    """Convert 05-12-2025 12:00 to Python datetime"""
    if not date_str or date_str.strip() == "":
        return None
    try:
        return datetime.strptime(date_str, "%d-%m-%Y %H:%M")
    except:
        logger.warning(f"⚠️ Invalid date format: {date_str}")
        return None


def import_templates(csv_file_path: str, update_existing: bool = False):

    csv_path = Path(csv_file_path)
    if not csv_path.exists():
        logger.error(f"❌ CSV not found: {csv_file_path}")
        return

    logger.info(f"📄 Reading CSV: {csv_file_path}")
    db = SessionLocal()

    added = updated = skipped = errors = 0

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            required = [
                "id", "name", "description", "prompt", "preview_image",
                "is_free", "is_active", "price", "currency",
                "is_archived", "archived_at", "display_order",
                "usage_count", "created_at", "updated_at"
            ]

            # Validate headers
            if not all(h in reader.fieldnames for h in required):
                logger.error(f"❌ CSV missing headers. Found: {reader.fieldnames}")
                return

            for row_num, row in enumerate(reader, start=2):
                try:
                    template_id = int(row["id"])
                    name = row["name"].strip()

                    existing = db.query(Template).filter(Template.id == template_id).first()

                    data = {
                        "id": template_id,
                        "name": name,
                        "description": row["description"],
                        "prompt": row["prompt"],
                        "preview_image": row["preview_image"],
                        "is_free": row["is_free"].lower() in ["true", "1", "yes"],
                        "is_active": row["is_active"].lower() in ["true", "1", "yes"],
                        "price": int(row["price"]),
                        "currency": row["currency"],
                        "is_archived": row["is_archived"].lower() in ["true", "1", "yes"],
                        "archived_at": parse_date(row["archived_at"]),
                        "display_order": int(row["display_order"]),
                        "usage_count": int(row["usage_count"]),
                        "created_at": parse_date(row["created_at"]),
                        "updated_at": parse_date(row["updated_at"])
                    }

                    if existing:
                        if update_existing:
                            for key, value in data.items():
                                setattr(existing, key, value)
                            logger.info(f"🔄 Updated row {row_num}: {name}")
                            updated += 1
                        else:
                            logger.info(f"⏭️ Skipped row {row_num}: {name} (exists)")
                            skipped += 1
                    else:
                        new_t = Template(**data)
                        db.add(new_t)
                        logger.info(f"✅ Added row {row_num}: {name}")
                        added += 1

                except Exception as e:
                    logger.error(f"❌ Error row {row_num}: {e}")
                    errors += 1

        db.commit()

    finally:
        db.close()

    logger.info("\n" + "="*50)
    logger.info("📊 IMPORT SUMMARY")
    logger.info("="*50)
    logger.info(f"Added: {added}")
    logger.info(f"Updated: {updated}")
    logger.info(f"Skipped: {skipped}")
    logger.info(f"Errors: {errors}")
    logger.info("="*50)


if __name__ == "__main__":
    import_templates("templates.csv", update_existing=True)
