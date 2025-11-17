from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:om%40123@localhost:5432/wedding_generator"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("SELECT version();"))
    print(result.fetchone())
