from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    jira_config = relationship("JiraConfig", back_populates="user", uselist=False, cascade="all, delete-orphan")
    projects = relationship("JiraProject", back_populates="user", cascade="all, delete-orphan")


class JiraConfig(Base):
    __tablename__ = "jira_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    jira_base_url = Column(String(512), nullable=False)
    jira_email = Column(String(255), nullable=False)
    jira_api_token = Column(Text, nullable=False)  # Encrypted in production
    gitlab_url = Column(String(512), nullable=True)  # e.g., https://gitlab.com
    gitlab_token = Column(Text, nullable=True)  # Personal access token
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="jira_config")


class JiraProject(Base):
    __tablename__ = "jira_projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_key = Column(String(50), nullable=False)
    project_name = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    gitlab_projects = Column(Text, nullable=True)  # Comma-separated list of GitLab project paths
    custom_instructions = Column(Text, nullable=True)  # Custom instructions for Claude
    embeddings_enabled = Column(Boolean, default=False)  # Beta: Enable meeting history with semantic search
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="projects")


# Embedding dimension for text-embedding-3-small
EMBEDDING_DIM = 1536


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_key = Column(String(50), nullable=False, index=True)
    title = Column(String(512), nullable=True)
    transcription = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)  # AI-generated summary
    tickets_created = Column(Text, nullable=True)  # JSON list of ticket keys
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    chunks = relationship("MeetingChunk", back_populates="meeting", cascade="all, delete-orphan")


class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("Meeting", back_populates="chunks")

    __table_args__ = (
        Index('ix_meeting_chunks_embedding', 'embedding', postgresql_using='ivfflat'),
    )


