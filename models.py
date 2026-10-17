from sqlalchemy import *
from database import Base

SAMPLE_DATA = {
    "Cash": 0,
    "Level": 0,
    "whitelisted": False,
    "wallets": {}
}

SAMPLE_STATS = {
    "Commands used": 0
}

class User(Base):
    __tablename__ = "users"
    
    uid = Column(String, primary_key=True, unique=True, index=True)
    stats = Column(JSON, default=SAMPLE_STATS.copy())
    data = Column(JSON, default=SAMPLE_DATA.copy())
    inventory = Column(JSON, default=[])
    emails = Column(JSON, default=[])
    blockedEmails = Column(JSON, default=[])
    storage = Column(Integer, default=0)
