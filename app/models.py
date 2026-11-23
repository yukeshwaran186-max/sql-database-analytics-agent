from sqlalchemy import Column, Integer, DateTime
from .database import Base

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_date = Column(DateTime, nullable=False)
