from sqlalchemy import Column, Integer, String, Float
from database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    landmark = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    