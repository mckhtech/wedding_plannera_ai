import pandas as pd
from sqlalchemy import create_engine

# Your database connection string
DATABASE_URL = "postgresql://postgres:om%40123@localhost:5432/wedding_generator"
engine = create_engine(DATABASE_URL)

# Read CSV
df = pd.read_csv('templates.csv')
# Import to database
df.to_sql('templates', engine, if_exists='replace', index=False)
