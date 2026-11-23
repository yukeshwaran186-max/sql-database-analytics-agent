import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database URL - SQLite file in the project root
DATABASE_URL = os.getenv("SQLITE_DB_URL", "sqlite:///./database.db")

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()

def init_db(seed_sample: bool = True):
    """Create database tables if they do not exist and seed sample data."""
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    if seed_sample:
        from app.models import Order
        from sqlalchemy.orm import Session
        from datetime import datetime, timedelta
        try:
            with Session(engine) as session:
                if session.query(Order).count() == 0:
                    for i in range(1, 11):
                        session.add(Order(order_date=datetime.now() - timedelta(days=10 - i)))
                    session.commit()
        except Exception:
            pass

def get_db():
    """Yield a database session for use in FastAPI/Streamlit dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def inspect_schema():
    """Return a dict mapping table names to a list of column names."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    schema = {}
    for table_name in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        schema[table_name] = columns
    return schema
