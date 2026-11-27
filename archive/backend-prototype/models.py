from sqlalchemy import Column, Text, BigInteger, Float
from database import Base


class TrainingData(Base):
    __tablename__ = "training_data"

    id = Column(Text, primary_key=True)
    url = Column(Text)
    landmark_id = Column(BigInteger)
    category_name = Column(Text)
    name = Column(Text)
    lat = Column(Float)
    lon = Column(Float)
    city = Column(Text)
    state = Column(Text)
    country = Column(Text)