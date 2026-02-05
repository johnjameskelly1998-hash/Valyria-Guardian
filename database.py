"""
Valyria Database - PostgreSQL Integration for Railway
Replaces JSON file storage with permanent database
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import logging

logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/valyria"
).replace("postgres://", "postgresql://", 1)  # Railway uses postgres:// but SQLAlchemy needs postgresql://

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(Base):
    """User profiles and preferences"""
    __tablename__ = "users"
    
    user_id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    preferences = Column(Text, default="{}")  # JSON string
    profile_data = Column(Text, default="{}")  # JSON string


class Conversation(Base):
    """Chat history and memories"""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_message = Column(Text, nullable=False)
    assistant_message = Column(Text, nullable=False)
    mode = Column(String, default="CHAT")  # CHAT, EMERGENCY, etc.


class BraceletData(Base):
    """Bracelet sensor data"""
    __tablename__ = "bracelet_data"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    heart_rate = Column(Integer)
    stress_level = Column(Integer)
    temperature = Column(Integer)
    battery_level = Column(Integer)
    emergency_detected = Column(Boolean, default=False)
    raw_data = Column(Text)  # JSON string of full data


class Memory(Base):
    """Long-term memories and important info"""
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    memory_type = Column(String)  # "important", "preference", "fact", etc.
    content = Column(Text, nullable=False)
    context = Column(Text)  # Additional context


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def init_database():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


# ============================================================================
# USER FUNCTIONS
# ============================================================================

def get_or_create_user(user_id: str) -> Dict[str, Any]:
    """Get user profile or create if doesn't exist"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            user = User(user_id=user_id, preferences="{}", profile_data="{}")
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"✅ Created new user: {user_id}")
        
        return {
            "user_id": user.user_id,
            "name": user.name,
            "preferences": json.loads(user.preferences or "{}"),
            "profile": json.loads(user.profile_data or "{}")
        }
    except Exception as e:
        logger.error(f"❌ Error getting user: {e}")
        db.rollback()
        return {"user_id": user_id, "preferences": {}, "profile": {}}
    finally:
        db.close()


def update_user_profile(user_id: str, **kwargs) -> bool:
    """Update user profile"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
        
        if "name" in kwargs:
            user.name = kwargs["name"]
        if "preferences" in kwargs:
            user.preferences = json.dumps(kwargs["preferences"])
        if "profile" in kwargs:
            user.profile_data = json.dumps(kwargs["profile"])
        
        db.commit()
        logger.info(f"✅ Updated user profile: {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error updating user: {e}")
        db.rollback()
        return False
    finally:
        db.close()


# ============================================================================
# CONVERSATION FUNCTIONS
# ============================================================================

def save_conversation(
    user_id: str,
    user_message: str,
    assistant_message: str,
    mode: str = "CHAT"
) -> bool:
    """Save conversation to database"""
    db = SessionLocal()
    try:
        conversation = Conversation(
            user_id=user_id,
            user_message=user_message,
            assistant_message=assistant_message,
            mode=mode
        )
        db.add(conversation)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Error saving conversation: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def get_conversation_history(
    user_id: str,
    limit: int = 50
) -> List[Dict[str, str]]:
    """Get recent conversation history"""
    db = SessionLocal()
    try:
        conversations = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.timestamp.desc())
            .limit(limit)
            .all()
        )
        
        return [
            {
                "user": conv.user_message,
                "assistant": conv.assistant_message,
                "timestamp": conv.timestamp.isoformat(),
                "mode": conv.mode
            }
            for conv in reversed(conversations)
        ]
    except Exception as e:
        logger.error(f"❌ Error getting conversation history: {e}")
        return []
    finally:
        db.close()


def clear_conversation_history(user_id: str) -> bool:
    """Clear conversation history for user"""
    db = SessionLocal()
    try:
        db.query(Conversation).filter(Conversation.user_id == user_id).delete()
        db.commit()
        logger.info(f"🗑️ Cleared conversation history: {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error clearing history: {e}")
        db.rollback()
        return False
    finally:
        db.close()


# ============================================================================
# BRACELET FUNCTIONS
# ============================================================================

def save_bracelet_data(user_id: str, data: Dict[str, Any]) -> bool:
    """Save bracelet sensor data"""
    db = SessionLocal()
    try:
        bracelet_data = BraceletData(
            user_id=user_id,
            heart_rate=data.get("heart_rate"),
            stress_level=data.get("stress_level"),
            temperature=data.get("temperature"),
            battery_level=data.get("battery_level"),
            emergency_detected=data.get("emergency_detected", False),
            raw_data=json.dumps(data)
        )
        db.add(bracelet_data)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Error saving bracelet data: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def get_recent_bracelet_data(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent bracelet sensor readings"""
    db = SessionLocal()
    try:
        data = (
            db.query(BraceletData)
            .filter(BraceletData.user_id == user_id)
            .order_by(BraceletData.timestamp.desc())
            .limit(limit)
            .all()
        )
        
        return [
            json.loads(reading.raw_data)
            for reading in reversed(data)
        ]
    except Exception as e:
        logger.error(f"❌ Error getting bracelet data: {e}")
        return []
    finally:
        db.close()


# ============================================================================
# MEMORY FUNCTIONS
# ============================================================================

def save_memory(
    user_id: str,
    content: str,
    memory_type: str = "general",
    context: Optional[str] = None
) -> bool:
    """Save important memory"""
    db = SessionLocal()
    try:
        memory = Memory(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            context=context
        )
        db.add(memory)
        db.commit()
        logger.info(f"💾 Saved memory for {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving memory: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def get_memories(user_id: str, memory_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get user memories"""
    db = SessionLocal()
    try:
        query = db.query(Memory).filter(Memory.user_id == user_id)
        
        if memory_type:
            query = query.filter(Memory.memory_type == memory_type)
        
        memories = query.order_by(Memory.created_at.desc()).all()
        
        return [
            {
                "content": mem.content,
                "type": mem.memory_type,
                "context": mem.context,
                "created_at": mem.created_at.isoformat()
            }
            for mem in memories
        ]
    except Exception as e:
        logger.error(f"❌ Error getting memories: {e}")
        return []
    finally:
        db.close()


# Initialize database on module import
try:
    init_database()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
