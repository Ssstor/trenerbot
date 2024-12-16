from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from api_token import DB_URL

engine = create_engine(DB_URL,
    pool_size=20,         # Размер пула (по умолчанию 5)
    max_overflow=10,      # Дополнительные соединения (по умолчанию 10)
    pool_timeout=30,      # Тайм-аут ожидания соединения в секундах (по умолчанию 30)
    pool_recycle=3600     # Рециклинг соединений (по умолчанию None)
)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, nullable=False)
    name = Column(String, nullable=False)
    measurements = relationship("Measurement", back_populates="user")
    first_measurement_date = Column(DateTime, nullable=False, default=datetime.utcnow)  

class Measurement(Base):
    __tablename__ = "measurements"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    version = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    weight = Column(Float)
    left_arm = Column(Float)
    right_arm = Column(Float)
    chest = Column(Float)
    waist = Column(Float)
    hips = Column(Float)
    left_leg = Column(Float)
    right_leg = Column(Float)

    user = relationship("User", back_populates="measurements")

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    time = Column(DateTime, nullable=False)
    user = relationship("User")

class UserState(Base):
    __tablename__ = "user_states"
    chat_id = Column(Integer, primary_key=True)
    step = Column(String, nullable=True)
    reminder_msg_id = Column(Integer)
    weight = Column(Float)
    left_arm = Column(Float)
    right_arm = Column(Float)
    chest = Column(Float)
    waist = Column(Float)
    hips = Column(Float)
    left_leg = Column(Float)
    right_leg = Column(Float)
    meditation_time = Column(String)
    meditation_video_message_id = Column(Integer)

if __name__ == "__main__":
    Base.metadata.create_all(engine)


