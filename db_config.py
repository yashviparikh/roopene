from sqlalchemy import create_engine

def get_engine():
    # Example: PostgreSQL connection
    DB_USER = "your_user"
    DB_PASS = "your_pass"
    DB_HOST = "localhost"
    DB_NAME = "your_db"

    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
    return engine
