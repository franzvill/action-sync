from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# Auth schemas
class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="User's email address", example="user@example.com")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)", example="securepassword123")
    full_name: Optional[str] = Field(None, description="User's full name", example="John Doe")


class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="User's email address", example="user@example.com")
    password: str = Field(..., description="User's password", example="securepassword123")


class UserResponse(BaseModel):
    id: int = Field(..., description="User ID")
    email: str = Field(..., description="User's email address")
    full_name: Optional[str] = Field(None, description="User's full name")
    created_at: datetime = Field(..., description="Account creation timestamp")

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(..., description="Token type (always 'bearer')")


class TokenData(BaseModel):
    email: Optional[str] = None


# Jira config schemas
class JiraConfigCreate(BaseModel):
    jira_base_url: str = Field(..., description="Jira instance URL", example="https://yourcompany.atlassian.net")
    jira_email: str = Field(..., description="Jira account email", example="user@company.com")
    jira_api_token: str = Field(..., description="Jira API token", example="your-jira-api-token")
    gitlab_url: Optional[str] = Field(None, description="GitLab instance URL", example="https://gitlab.com")
    gitlab_token: Optional[str] = Field(None, description="GitLab access token", example="your-gitlab-token")


class JiraConfigResponse(BaseModel):
    id: int = Field(..., description="Configuration ID")
    jira_base_url: str = Field(..., description="Jira instance URL")
    jira_email: str = Field(..., description="Jira account email")
    gitlab_url: Optional[str] = Field(None, description="GitLab instance URL")
    has_gitlab: bool = Field(False, description="Whether GitLab is configured")
    created_at: datetime = Field(..., description="Configuration creation timestamp")

    class Config:
        from_attributes = True


class JiraConfigUpdate(BaseModel):
    jira_base_url: Optional[str] = Field(None, description="Jira instance URL")
    jira_email: Optional[str] = Field(None, description="Jira account email")
    jira_api_token: Optional[str] = Field(None, description="Jira API token")
    gitlab_url: Optional[str] = Field(None, description="GitLab instance URL")
    gitlab_token: Optional[str] = Field(None, description="GitLab access token")


# Jira project schemas
class JiraProjectCreate(BaseModel):
    project_key: str = Field(..., description="Jira project key", example="PROJ")
    project_name: Optional[str] = Field(None, description="Project display name", example="My Project")
    is_default: bool = Field(False, description="Set as default project")
    gitlab_projects: Optional[str] = Field(None, description="Comma-separated GitLab project paths", example="group/repo1,group/repo2")
    custom_instructions: Optional[str] = Field(None, description="Custom AI instructions", example="Focus on backend tasks")
    embeddings_enabled: bool = Field(False, description="Enable semantic search for meetings")
    kanban_jql: Optional[str] = Field(None, description="Custom JQL for Kanban board", example="project = PROJ AND status != Done")


class JiraProjectResponse(BaseModel):
    id: int = Field(..., description="Project configuration ID")
    project_key: str = Field(..., description="Jira project key")
    project_name: Optional[str] = Field(None, description="Project display name")
    is_default: bool = Field(..., description="Whether this is the default project")
    gitlab_projects: Optional[str] = Field(None, description="Comma-separated GitLab project paths")
    custom_instructions: Optional[str] = Field(None, description="Custom AI instructions")
    embeddings_enabled: bool = Field(False, description="Whether semantic search is enabled")
    kanban_jql: Optional[str] = Field(None, description="Custom JQL for Kanban board")
    created_at: datetime = Field(..., description="Configuration creation timestamp")

    class Config:
        from_attributes = True


class JiraProjectUpdate(BaseModel):
    gitlab_projects: Optional[str] = Field(None, description="Comma-separated GitLab project paths")
    custom_instructions: Optional[str] = Field(None, description="Custom AI instructions")
    embeddings_enabled: Optional[bool] = Field(None, description="Enable/disable semantic search")
    kanban_jql: Optional[str] = Field(None, description="Custom JQL for Kanban board")


# Meeting schemas
class MeetingProcessRequest(BaseModel):
    transcription: str = Field(..., description="Meeting transcription text", example="We discussed implementing a new user authentication system...")
    project_key: str = Field(..., description="Target Jira project key", example="PROJ")


# Question schemas
class JiraQuestionRequest(BaseModel):
    question: str = Field(..., description="Question about the project", example="What are the open high-priority bugs?")
    project_key: str = Field(..., description="Jira project key to query", example="PROJ")


# Work schemas
class WorkStartRequest(BaseModel):
    project_id: int = Field(..., description="Project configuration ID", example=1)
    issue_key: str = Field(..., description="Jira issue key", example="PROJ-123")
