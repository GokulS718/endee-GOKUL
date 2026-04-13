from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base
import datetime

class Query(Base):
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, index=True)
    user_input = Column(String, nullable=False)
    input_type = Column(String, default="text") # 'url' or 'text'
    prediction_result = Column(String, nullable=False)
    confidence_score = Column(Float, nullable=False)
    safety_status = Column(String, default="Unknown")
    source_links = Column(String, default="[]") # JSON list
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class NewsFact(Base):
    __tablename__ = "news_facts"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, nullable=False)
    source_url = Column(String)
    topic = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
