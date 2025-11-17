"""
Run this migration to add archive fields to templates table
"""

# If using Alembic:
# alembic revision --autogenerate -m "Add archive fields to templates"
# alembic upgrade head

# Or run this SQL directly in your database:
"""
ALTER TABLE templates ADD COLUMN is_archived BOOLEAN DEFAULT FALSE;
ALTER TABLE templates ADD COLUMN archived_at TIMESTAMP NULL;
UPDATE templates SET is_archived = FALSE WHERE is_archived IS NULL;
"""