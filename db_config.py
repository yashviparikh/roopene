from sqlalchemy import create_engine
import os

def get_engine():
    """
    SQLite database configuration (offline, single-user).
    Database file will be created automatically if it does not exist.
    """

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    db_path = "data/app.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False}
    )

    return engine
