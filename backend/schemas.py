from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


# Auth schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


# Jira config schemas
class JiraConfigCreate(BaseModel):
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    gitlab_url: Optional[str] = None
    gitlab_token: Optional[str] = None


class JiraConfigResponse(BaseModel):
    id: int
    jira_base_url: str
    jira_email: str
    gitlab_url: Optional[str] = None
    has_gitlab: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class JiraConfigUpdate(BaseModel):
    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    gitlab_url: Optional[str] = None
    gitlab_token: Optional[str] = None


# Jira project schemas
class JiraProjectCreate(BaseModel):
    project_key: str
    project_name: Optional[str] = None
    is_default: bool = False
    gitlab_projects: Optional[str] = None  # Comma-separated list
    custom_instructions: Optional[str] = None  # Custom instructions for Claude
    embeddings_enabled: bool = False  # Beta: Enable meeting history with semantic search
    kanban_jql: Optional[str] = None  # JQL filter for Kanban board


class JiraProjectResponse(BaseModel):
    id: int
    project_key: str
    project_name: Optional[str]
    is_default: bool
    gitlab_projects: Optional[str] = None
    custom_instructions: Optional[str] = None
    embeddings_enabled: bool = False
    kanban_jql: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class JiraProjectUpdate(BaseModel):
    gitlab_projects: Optional[str] = None
    custom_instructions: Optional[str] = None
    embeddings_enabled: Optional[bool] = None
    kanban_jql: Optional[str] = None


# Meeting schemas
class MeetingProcessRequest(BaseModel):
    transcription: str
    project_key: str


# Question schemas
class JiraQuestionRequest(BaseModel):
    question: str
    project_key: str
    session_id: Optional[str] = None  # For continuing conversations


# Work schemas
class WorkStartRequest(BaseModel):
    project_id: int
    issue_key: str
