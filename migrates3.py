"""
Migrate existing local files to S3 (NO ACLs)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from app.services.s3_service import s3_service
from app.database import SessionLocal
from app.models.generation import Generation
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_directory(local_dir: str, s3_folder: str):
    """
    Upload all files from a local directory to S3/{s3_folder}
    ACL is automatically NOT used (because s3_service handles it)
    """
    dir_path = Path(local_dir)

    if not dir_path.exists():
        logger.warning(f"Directory not found: {local_dir}")
        return 0

    files = list(dir_path.rglob("*"))
    logger.info(f"\n📁 Migrating {len(files)} files from {local_dir} → S3/{s3_folder}")

    migrated = 0
    failed = 0

    for file_path in files:
        if file_path.is_file():
            try:
                key = f"{s3_folder}/{file_path.name}"

                logger.info(f"⬆️ Uploading: {file_path} → {key}")

                # upload (NO ACL automatically)
                s3_url = s3_service.upload_file(
                    file_path=str(file_path),
                    folder=s3_folder
                )

                logger.info(f"   ✅ Uploaded: {s3_url}")
                migrated += 1

            except Exception as e:
                logger.error(f"   ❌ Failed: {file_path} → {str(e)}")
                failed += 1

    logger.info(f"\n✅ Migrated: {migrated}/{len(files)} files")
    if failed > 0:
        logger.warning(f"⚠️ Failed: {failed} files")

    return migrated


def update_database_paths():
    """
    Update database records to use S3 URLs instead of local file paths.
    """
    logger.info("\n" + "=" * 60)
    logger.info("🗄️ UPDATING DATABASE PATHS")
    logger.info("=" * 60)

    db = SessionLocal()

    try:
        generations = db.query(Generation).filter(
            Generation.generated_image_path.isnot(None),
            ~Generation.generated_image_path.like("http%")
        ).all()

        logger.info(f"Found {len(generations)} records to update")

        updated = 0

        for gen in generations:
            try:
                filename = Path(gen.generated_image_path).name
                gen.generated_image_path = (
                    f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/generated/{filename}"
                )

                if gen.watermarked_image_path and not gen.watermarked_image_path.startswith("http"):
                    wm = Path(gen.watermarked_image_path).name
                    gen.watermarked_image_path = (
                        f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/generated/{wm}"
                    )

                updated += 1
                logger.info(f"   🔄 Updated gen #{gen.id}")

            except Exception as e:
                logger.error(f"❌ Failed to update #{gen.id}: {str(e)}")

        db.commit()
        logger.info(f"\n✅ Updated {updated} DB records")

    except Exception as e:
        logger.error(f"❌ DB update error: {e}")
        db.rollback()
    finally:
        db.close()


def main():
    print("\n" + "=" * 60)
    print("🚀 LOCAL → S3 MIGRATION TOOL (ACL FREE)")
    print("=" * 60)

    if not settings.USE_S3:
        print("❌ USE_S3=false — aborting")
        return

    response = input("\nContinue? (yes/no): ")
    if response.lower() != "yes":
        print("Cancelled.")
        return

    total = 0
    total += migrate_directory(settings.UPLOAD_DIR, "uploads")
    total += migrate_directory(settings.GENERATED_DIR, "generated")
    total += migrate_directory(settings.TEMPLATE_PREVIEW_DIR, "template_previews")

    print("\n" + "=" * 60)
    print(f"✅ Uploaded {total} files")
    print("=" * 60)

    response = input("\nUpdate DB paths? (yes/no): ")
    if response.lower() == "yes":
        update_database_paths()

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
