import json
import asyncio
from datetime import timedelta
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, init_db, async_session_maker
from models import User, JiraConfig, JiraProject, Meeting
from schemas import (
    UserCreate, UserLogin, UserResponse, Token,
    JiraConfigCreate, JiraConfigResponse, JiraConfigUpdate,
    JiraProjectCreate, JiraProjectResponse, JiraProjectUpdate,
    MeetingProcessRequest, JiraQuestionRequest, WorkStartRequest
)
from auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user
)
from config import get_settings
from meeting_processor import process_meeting_transcription, ask_jira_question
from work_processor import clone_repos_for_work, process_work_ticket
from session_manager import session_manager
from embedding_service import (
    store_meeting_with_embeddings, semantic_search, get_meetings, get_meeting_detail
)
from jira_tools import JiraClient

settings = get_settings()


# Global state for current processing task
class ProcessingState:
    def __init__(self):
        self.is_processing = False
        self.current_task: Optional[asyncio.Task] = None
        self.current_user_id: Optional[int] = None

    def abort(self):
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        self.is_processing = False
        self.current_task = None
        self.current_user_id = None


processing_state = ProcessingState()


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        # Support multiple connections per user (multiple tabs/windows)
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_message(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            dead_connections = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_connections.append(ws)
            # Clean up dead connections
            for ws in dead_connections:
                self.disconnect(user_id, ws)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await session_manager.start()
    yield
    await session_manager.stop()


app = FastAPI(
    title="ActionSync API",
    description="""🚀 **ActionSync** - AI-powered meeting transcription to Jira ticket conversion
    
    ## Features
    * 🎯 Convert meeting transcriptions into structured Jira tickets
    * 🔐 Secure JWT-based authentication
    * 📊 Kanban board integration
    * 🔍 Semantic search across meeting history
    * 🤖 AI-powered work automation
    * 🔗 GitLab integration for code management
    
    ## Authentication
    Most endpoints require Bearer token authentication. Get your token from `/api/auth/login`.
    
    ## Getting Started
    1. Register a new account at `/api/auth/register`
    2. Login to get your access token at `/api/auth/login`
    3. Configure your Jira settings at `/api/jira/config`
    4. Add your projects at `/api/jira/projects`
    5. Start processing meetings at `/api/meetings/process`
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "ActionSync Support",
        "url": "https://github.com/your-repo/action-sync",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    tags_metadata=[
        {
            "name": "Authentication",
            "description": "User registration, login, and profile management",
        },
        {
            "name": "Jira Configuration",
            "description": "Manage Jira and GitLab integration settings",
        },
        {
            "name": "Projects",
            "description": "Manage Jira projects and their configurations",
        },
        {
            "name": "Meetings",
            "description": "Process meeting transcriptions and manage meeting history",
        },
        {
            "name": "Kanban",
            "description": "Kanban board operations and ticket management",
        },
        {
            "name": "AI Work",
            "description": "AI-powered ticket processing and automation",
        },
        {
            "name": "Processing",
            "description": "Background task management and status monitoring",
        },
        {
            "name": "WebSocket",
            "description": "Real-time communication for processing updates",
        },
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Auth Routes ============

@app.post(
    "/api/auth/register", 
    response_model=UserResponse, 
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
    summary="Register a new user",
    description="Create a new user account with email and password. Email must be unique.",
    responses={
        201: {"description": "User successfully created"},
        400: {"description": "Email already registered or validation error"},
    }
)
async def register(
    user_data: UserCreate = {
        "example": {
            "email": "user@example.com",
            "password": "securepassword123",
            "full_name": "John Doe"
        }
    }, 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@app.post(
    "/api/auth/login", 
    response_model=Token,
    tags=["Authentication"],
    summary="User login",
    description="Authenticate user and return JWT access token for API access.",
    responses={
        200: {"description": "Login successful, returns access token"},
        401: {"description": "Invalid credentials"},
    }
)
async def login(
    user_data: UserLogin = {
        "example": {
            "email": "user@example.com",
            "password": "securepassword123"
        }
    }, 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get(
    "/api/auth/me", 
    response_model=UserResponse,
    tags=["Authentication"],
    summary="Get current user profile",
    description="Retrieve the profile information of the currently authenticated user.",
    responses={
        200: {"description": "User profile retrieved successfully"},
        401: {"description": "Authentication required"},
    }
)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ============ Jira Config Routes ============

@app.get(
    "/api/jira/config", 
    response_model=Optional[JiraConfigResponse],
    tags=["Jira Configuration"],
    summary="Get Jira configuration",
    description="Retrieve the current user's Jira and GitLab integration settings.",
    responses={
        200: {"description": "Configuration retrieved (may be null if not set)"},
        401: {"description": "Authentication required"},
    }
)
async def get_jira_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    config = result.scalar_one_or_none()
    if config:
        # Compute has_gitlab dynamically
        config.has_gitlab = bool(config.gitlab_token)
    return config


@app.post(
    "/api/jira/config", 
    response_model=JiraConfigResponse, 
    status_code=status.HTTP_201_CREATED,
    tags=["Jira Configuration"],
    summary="Create Jira configuration",
    description="Set up Jira and GitLab integration settings. Required for processing meetings.",
    responses={
        201: {"description": "Configuration created successfully"},
        400: {"description": "Configuration already exists or validation error"},
        401: {"description": "Authentication required"},
    }
)
async def create_jira_config(
    config_data: JiraConfigCreate = {
        "example": {
            "jira_base_url": "https://yourcompany.atlassian.net",
            "jira_email": "user@company.com",
            "jira_api_token": "your-jira-api-token",
            "gitlab_url": "https://gitlab.com",
            "gitlab_token": "your-gitlab-token"
        }
    },
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira config already exists. Use PUT to update.")

    config = JiraConfig(
        user_id=current_user.id,
        jira_base_url=config_data.jira_base_url.rstrip("/"),
        jira_email=config_data.jira_email,
        jira_api_token=config_data.jira_api_token,
        gitlab_url=config_data.gitlab_url.rstrip("/") if config_data.gitlab_url else None,
        gitlab_token=config_data.gitlab_token
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    config.has_gitlab = bool(config.gitlab_token)
    return config


@app.put(
    "/api/jira/config", 
    response_model=JiraConfigResponse,
    tags=["Jira Configuration"],
    summary="Update Jira configuration",
    description="Update existing Jira and GitLab integration settings. Only provided fields will be updated.",
    responses={
        200: {"description": "Configuration updated successfully"},
        404: {"description": "Configuration not found"},
        401: {"description": "Authentication required"},
    }
)
async def update_jira_config(
    config_data: JiraConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jira config not found")

    if config_data.jira_base_url:
        config.jira_base_url = config_data.jira_base_url.rstrip("/")
    if config_data.jira_email:
        config.jira_email = config_data.jira_email
    if config_data.jira_api_token:
        config.jira_api_token = config_data.jira_api_token
    if config_data.gitlab_url is not None:
        config.gitlab_url = config_data.gitlab_url.rstrip("/") if config_data.gitlab_url else None
    if config_data.gitlab_token is not None:
        config.gitlab_token = config_data.gitlab_token if config_data.gitlab_token else None

    await db.commit()
    await db.refresh(config)
    config.has_gitlab = bool(config.gitlab_token)
    return config


# ============ Jira Projects Routes ============

@app.get(
    "/api/jira/projects", 
    response_model=List[JiraProjectResponse],
    tags=["Projects"],
    summary="List Jira projects",
    description="Get all configured Jira projects for the current user.",
    responses={
        200: {"description": "List of configured projects"},
        401: {"description": "Authentication required"},
    }
)
async def get_jira_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(JiraProject).where(JiraProject.user_id == current_user.id))
    return result.scalars().all()


@app.post(
    "/api/jira/projects", 
    response_model=JiraProjectResponse, 
    status_code=status.HTTP_201_CREATED,
    tags=["Projects"],
    summary="Add Jira project",
    description="Add a new Jira project to your configuration with optional GitLab integration.",
    responses={
        201: {"description": "Project added successfully"},
        400: {"description": "Project already exists or validation error"},
        401: {"description": "Authentication required"},
    }
)
async def add_jira_project(
    project_data: JiraProjectCreate = {
        "example": {
            "project_key": "PROJ",
            "project_name": "My Project",
            "is_default": True,
            "gitlab_projects": "group/repo1,group/repo2",
            "custom_instructions": "Focus on backend tasks",
            "embeddings_enabled": True,
            "kanban_jql": "project = PROJ AND status != Done"
        }
    },
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == project_data.project_key.upper()
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project already added")

    if project_data.is_default:
        existing = await db.execute(select(JiraProject).where(JiraProject.user_id == current_user.id))
        for proj in existing.scalars().all():
            proj.is_default = False

    project = JiraProject(
        user_id=current_user.id,
        project_key=project_data.project_key.upper(),
        project_name=project_data.project_name,
        is_default=project_data.is_default,
        gitlab_projects=project_data.gitlab_projects,
        custom_instructions=project_data.custom_instructions,
        embeddings_enabled=project_data.embeddings_enabled,
        kanban_jql=project_data.kanban_jql
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@app.delete(
    "/api/jira/projects/{project_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Projects"],
    summary="Delete Jira project",
    description="Remove a Jira project from your configuration.",
    responses={
        204: {"description": "Project deleted successfully"},
        404: {"description": "Project not found"},
        401: {"description": "Authentication required"},
    }
)
async def delete_jira_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(JiraProject).where(JiraProject.id == project_id, JiraProject.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await db.delete(project)
    await db.commit()


@app.put(
    "/api/jira/projects/{project_id}", 
    response_model=JiraProjectResponse,
    tags=["Projects"],
    summary="Update Jira project",
    description="Update project settings including GitLab repositories and custom instructions.",
    responses={
        200: {"description": "Project updated successfully"},
        404: {"description": "Project not found"},
        401: {"description": "Authentication required"},
    }
)
async def update_jira_project(
    project_id: int,
    project_data: JiraProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    print(f"[DEBUG] update_jira_project called with data: {project_data}")
    result = await db.execute(
        select(JiraProject).where(JiraProject.id == project_id, JiraProject.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project_data.gitlab_projects is not None:
        print(f"[DEBUG] Setting gitlab_projects from '{project.gitlab_projects}' to '{project_data.gitlab_projects}'")
        project.gitlab_projects = project_data.gitlab_projects if project_data.gitlab_projects else None
    if project_data.custom_instructions is not None:
        project.custom_instructions = project_data.custom_instructions if project_data.custom_instructions else None
    if project_data.embeddings_enabled is not None:
        project.embeddings_enabled = project_data.embeddings_enabled
    if project_data.kanban_jql is not None:
        project.kanban_jql = project_data.kanban_jql if project_data.kanban_jql else None

    await db.commit()
    await db.refresh(project)
    return project


# ============ Kanban Routes ============

@app.get(
    "/api/jira/workflow/{project_key}",
    tags=["Kanban"],
    summary="Get workflow statuses",
    description="Retrieve available workflow statuses for Kanban board columns.",
    responses={
        200: {"description": "Workflow statuses retrieved successfully"},
        404: {"description": "Project not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Jira API error"},
    }
)
async def get_workflow_statuses(
    project_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify user has this project configured
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == project_key.upper()
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira not configured")

    client = JiraClient(jira_config.jira_base_url, jira_config.jira_email, jira_config.jira_api_token)

    try:
        statuses = await client.get_workflow_statuses(project_key.upper())
        return {"statuses": statuses}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get(
    "/api/jira/kanban/{project_key}",
    tags=["Kanban"],
    summary="Get Kanban tickets",
    description="Retrieve tickets for Kanban board using project's JQL filter or default query.",
    responses={
        200: {"description": "Kanban tickets retrieved successfully"},
        404: {"description": "Project not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Jira API error"},
    }
)
async def get_kanban_tickets(
    project_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Get project with its settings
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == project_key.upper()
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira not configured")

    # Build JQL - use custom or default
    if project.kanban_jql:
        jql = project.kanban_jql
    else:
        jql = f"project = {project_key.upper()} ORDER BY updated DESC"

    client = JiraClient(jira_config.jira_base_url, jira_config.jira_email, jira_config.jira_api_token)

    try:
        issues = await client.search_issues(jql)
        return {"issues": issues, "jql": jql}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get(
    "/api/jira/ticket/{issue_key}",
    tags=["Kanban"],
    summary="Get ticket details",
    description="Retrieve full details of a specific Jira ticket by issue key (e.g., PROJ-123).",
    responses={
        200: {"description": "Ticket details retrieved successfully"},
        400: {"description": "Invalid issue key format"},
        404: {"description": "Project or ticket not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Jira API error"},
    }
)
async def get_ticket_details(
    issue_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Validate issue key format (e.g., PROJ-123)
    if "-" not in issue_key or not issue_key.split("-")[1].isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid issue key format")

    # Extract project key from issue key
    project_key = issue_key.split("-")[0].upper()

    # Verify user has this project
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == project_key
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira not configured")

    client = JiraClient(jira_config.jira_base_url, jira_config.jira_email, jira_config.jira_api_token)

    try:
        ticket = await client.get_issue_full(issue_key)
        return ticket
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post(
    "/api/work/start",
    tags=["AI Work"],
    summary="Start AI work on ticket",
    description="Begin AI-powered work on a Jira ticket including code analysis and implementation.",
    responses={
        200: {"description": "AI work started successfully"},
        400: {"description": "Invalid request or missing configuration"},
        404: {"description": "Project not found"},
        409: {"description": "Another task is already processing"},
        401: {"description": "Authentication required"},
    }
)
async def start_work(
    work_data: WorkStartRequest = {
        "example": {
            "project_id": 1,
            "issue_key": "PROJ-123"
        }
    },
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if processing_state.is_processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another task is being processed. Please wait or abort it."
        )

    # Get project
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.id == work_data.project_id,
            JiraProject.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Verify issue belongs to project
    if not work_data.issue_key.upper().startswith(f"{project.project_key}-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Issue does not belong to this project")

    # Get Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira not configured")

    # Verify GitLab is configured
    if not jira_config.gitlab_url or not jira_config.gitlab_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitLab not configured")

    if not project.gitlab_projects:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No GitLab repositories configured for this project")

    # Start processing
    processing_state.is_processing = True
    processing_state.current_user_id = current_user.id

    task = asyncio.create_task(
        _work_ticket_task(
            issue_key=work_data.issue_key.upper(),
            project_key=project.project_key,
            jira_base_url=jira_config.jira_base_url,
            jira_email=jira_config.jira_email,
            jira_api_token=jira_config.jira_api_token,
            gitlab_url=jira_config.gitlab_url,
            gitlab_token=jira_config.gitlab_token,
            gitlab_projects=project.gitlab_projects,
            custom_instructions=project.custom_instructions,
            user_id=current_user.id
        )
    )
    processing_state.current_task = task

    return {"status": "started"}


async def _work_ticket_task(
    issue_key: str,
    project_key: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    gitlab_url: str,
    gitlab_token: str,
    gitlab_projects: str,
    custom_instructions: Optional[str],
    user_id: int
):
    """Background task for AI ticket work."""

    async def message_callback(message: dict):
        print(f"[WORK DEBUG] Sending message: {message.get('type')}")
        await manager.send_message(user_id, message)

    try:
        # Get full ticket details
        print(f"[WORK DEBUG] Starting work on {issue_key}")
        await message_callback({"type": "text", "content": f"Fetching ticket {issue_key}...\n"})
        client = JiraClient(jira_base_url, jira_email, jira_api_token)
        ticket = await client.get_issue_full(issue_key)
        await message_callback({"type": "text", "content": f"Ticket: {ticket['summary']}\n\n"})

        # Clone repositories
        print(f"[WORK DEBUG] Cloning repositories...")
        project_list = [p.strip() for p in gitlab_projects.split(",") if p.strip()]
        # Use Jira email for git author
        git_author_name = jira_email.split("@")[0].replace(".", " ").title()
        work_dir = await clone_repos_for_work(
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token,
            project_paths=project_list,
            issue_key=issue_key,
            git_author_name=git_author_name,
            git_author_email=jira_email,
            callback=message_callback
        )
        print(f"[WORK DEBUG] Cloning complete, work_dir={work_dir}")

        await message_callback({"type": "text", "content": "\nStarting AI work...\n\n"})
        print(f"[WORK DEBUG] Invoking Claude...")

        # Process the ticket
        result = await process_work_ticket(
            ticket=ticket,
            project_key=project_key,
            jira_base_url=jira_base_url,
            jira_email=jira_email,
            jira_api_token=jira_api_token,
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token,
            work_dir=work_dir,
            message_callback=message_callback,
            custom_instructions=custom_instructions
        )

        await manager.send_message(user_id, {
            "type": "complete",
            "success": result["success"],
            "summary": result.get("summary", "")
        })

    except asyncio.CancelledError:
        await manager.send_message(user_id, {"type": "aborted"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        await manager.send_message(user_id, {"type": "error", "error": str(e)})
    finally:
        processing_state.is_processing = False
        processing_state.current_task = None
        processing_state.current_user_id = None


# ============ Meeting Processing Routes ============

@app.get(
    "/api/processing/status",
    tags=["Processing"],
    summary="Get processing status",
    description="Check if any background processing task is currently running.",
    responses={
        200: {"description": "Processing status retrieved"},
        401: {"description": "Authentication required"},
    }
)
async def get_processing_status(current_user: User = Depends(get_current_user)):
    return {
        "is_processing": processing_state.is_processing,
        "is_mine": processing_state.current_user_id == current_user.id
    }


@app.post(
    "/api/processing/abort",
    tags=["Processing"],
    summary="Abort processing task",
    description="Cancel the currently running background processing task.",
    responses={
        200: {"description": "Task aborted successfully"},
        400: {"description": "No task is currently processing"},
        403: {"description": "Cannot abort another user's task"},
        401: {"description": "Authentication required"},
    }
)
async def abort_processing(current_user: User = Depends(get_current_user)):
    if not processing_state.is_processing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No task is processing")

    if processing_state.current_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot abort another user's task")

    processing_state.abort()
    await manager.send_message(current_user.id, {"type": "aborted"})
    return {"status": "aborted"}


@app.post(
    "/api/meetings/process",
    tags=["Meetings"],
    summary="Process meeting transcription",
    description="Convert meeting transcription into structured Jira tickets using AI.",
    responses={
        200: {"description": "Meeting processing started"},
        400: {"description": "Invalid request or missing configuration"},
        409: {"description": "Another meeting is being processed"},
        401: {"description": "Authentication required"},
    }
)
async def process_meeting(
    meeting_data: MeetingProcessRequest = {
        "example": {
            "transcription": "We discussed implementing a new user authentication system...",
            "project_key": "PROJ"
        }
    },
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if processing_state.is_processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another meeting is being processed. Please wait or abort it."
        )

    # Get user's Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please configure your Jira settings first")

    # Verify project is in user's list
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == meeting_data.project_key.upper()
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not in your configured projects list")

    # Start processing
    processing_state.is_processing = True
    processing_state.current_user_id = current_user.id

    task = asyncio.create_task(
        _process_meeting_task(
            meeting_data.transcription,
            meeting_data.project_key.upper(),
            jira_config.jira_base_url,
            jira_config.jira_email,
            jira_config.jira_api_token,
            current_user.id,
            gitlab_url=jira_config.gitlab_url,
            gitlab_token=jira_config.gitlab_token,
            gitlab_projects=project.gitlab_projects,
            custom_instructions=project.custom_instructions,
            embeddings_enabled=project.embeddings_enabled
        )
    )
    processing_state.current_task = task

    return {"status": "started"}


async def _process_meeting_task(
    transcription: str,
    project_key: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    user_id: int,
    gitlab_url: Optional[str] = None,
    gitlab_token: Optional[str] = None,
    gitlab_projects: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    embeddings_enabled: bool = False
):
    print(f"[DEBUG] Starting meeting processing for user {user_id}, project {project_key}")

    async def message_callback(message: dict):
        print(f"[DEBUG] Sending message: {message.get('type')}")
        await manager.send_message(user_id, message)

    try:
        print("[DEBUG] Calling process_meeting_transcription...")
        result = await process_meeting_transcription(
            transcription=transcription,
            project_key=project_key,
            jira_base_url=jira_base_url,
            jira_email=jira_email,
            jira_api_token=jira_api_token,
            message_callback=message_callback,
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token,
            gitlab_projects=gitlab_projects,
            custom_instructions=custom_instructions,
            user_id=user_id
        )

        # Store the meeting with embeddings (only if feature is enabled for this project)
        if result.get("success") and embeddings_enabled:
            try:
                await message_callback({"type": "text", "content": "\n📝 Storing meeting and generating embeddings...\n"})
                async with async_session_maker() as db:
                    meeting = await store_meeting_with_embeddings(
                        db=db,
                        user_id=user_id,
                        project_key=project_key,
                        transcription=transcription,
                        summary=result.get("summary"),
                        tickets_created=result.get("tickets_created", []),
                        title=f"Meeting - {project_key}"
                    )
                    await message_callback({"type": "text", "content": f"✅ Meeting stored (ID: {meeting.id})\n"})
            except Exception as e:
                print(f"Error storing meeting: {e}")
                await message_callback({"type": "text", "content": f"⚠️ Could not store meeting: {e}\n"})

        await manager.send_message(user_id, {
            "type": "complete",
            "success": result["success"],
            "summary": result.get("summary", "")
        })
        print("[DEBUG] Processing completed successfully")

    except asyncio.CancelledError:
        print("[DEBUG] Task cancelled")
        await manager.send_message(user_id, {"type": "aborted"})
    except Exception as e:
        print(f"[DEBUG] Error in processing: {e}")
        import traceback
        traceback.print_exc()
        await manager.send_message(user_id, {"type": "error", "error": str(e)})
    finally:
        processing_state.is_processing = False
        processing_state.current_task = None
        processing_state.current_user_id = None


# ============ Ask Question ============

@app.post(
    "/api/jira/ask",
    tags=["AI Work"],
    summary="Ask AI about project",
    description="Ask AI questions about your Jira project and get intelligent responses.",
    responses={
        200: {"description": "Question processing started"},
        400: {"description": "Invalid request or missing configuration"},
        409: {"description": "Another task is being processed"},
        401: {"description": "Authentication required"},
    }
)
async def ask_question(
    question_data: JiraQuestionRequest = {
        "example": {
            "question": "What are the open high-priority bugs in this project?",
            "project_key": "PROJ"
        }
    },
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if processing_state.is_processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another task is being processed. Please wait or abort it."
        )

    # Get user's Jira config
    result = await db.execute(select(JiraConfig).where(JiraConfig.user_id == current_user.id))
    jira_config = result.scalar_one_or_none()
    if not jira_config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please configure your Jira settings first")

    # Get project with its settings
    result = await db.execute(
        select(JiraProject).where(
            JiraProject.user_id == current_user.id,
            JiraProject.project_key == question_data.project_key.upper()
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not in your configured projects list")

    # Start processing
    processing_state.is_processing = True
    processing_state.current_user_id = current_user.id

    task = asyncio.create_task(
        _ask_question_task(
            question_data.question,
            question_data.project_key.upper(),
            jira_config.jira_base_url,
            jira_config.jira_email,
            jira_config.jira_api_token,
            current_user.id,
            jira_config.gitlab_url,
            jira_config.gitlab_token,
            project.gitlab_projects,
            question_data.session_id
        )
    )
    processing_state.current_task = task

    return {"status": "started"}


async def _ask_question_task(
    question: str,
    project_key: str,
    jira_base_url: str,
    jira_email: str,
    jira_api_token: str,
    user_id: int,
    gitlab_url: str = None,
    gitlab_token: str = None,
    gitlab_projects: str = None,
    session_id: str = None
):
    async def message_callback(message: dict):
        await manager.send_message(user_id, message)

    try:
        result = await ask_jira_question(
            question=question,
            project_key=project_key,
            jira_base_url=jira_base_url,
            jira_email=jira_email,
            jira_api_token=jira_api_token,
            message_callback=message_callback,
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token,
            gitlab_projects=gitlab_projects,
            user_id=user_id,
            session_id=session_id
        )

        await manager.send_message(user_id, {
            "type": "complete",
            "success": result["success"],
            "answer": result.get("answer", ""),
            "session_id": result.get("session_id")
        })

    except asyncio.CancelledError:
        await manager.send_message(user_id, {"type": "aborted"})
    except Exception as e:
        await manager.send_message(user_id, {"type": "error", "error": str(e)})
    finally:
        processing_state.is_processing = False
        processing_state.current_task = None
        processing_state.current_user_id = None


# ============ WebSocket ============

@app.websocket(
    "/ws",
    tags=["WebSocket"],
    summary="WebSocket connection",
    description="Establish WebSocket connection for real-time processing updates. Requires JWT token as query parameter."
)
async def websocket_endpoint(websocket: WebSocket, token: str):
    from jose import JWTError, jwt
    from database import async_session_maker

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email = payload.get("sub")
        if not email:
            await websocket.close(code=4001)
            return

        async with async_session_maker() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                await websocket.close(code=4001)
                return
            user_id = user.id

        await manager.connect(user_id, websocket)
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect(user_id, websocket)
    except JWTError:
        await websocket.close(code=4001)


# ============ Meetings History & Search ============

@app.get(
    "/api/meetings",
    tags=["Meetings"],
    summary="List meetings",
    description="Retrieve paginated list of past meetings with optional project filtering.",
    responses={
        200: {"description": "Meetings retrieved successfully"},
        401: {"description": "Authentication required"},
    }
)
async def list_meetings(
    project_key: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    meetings = await get_meetings(
        db=db,
        user_id=current_user.id,
        project_key=project_key.upper() if project_key else None,
        limit=limit,
        offset=offset
    )
    return {"meetings": meetings}


@app.get(
    "/api/meetings/{meeting_id}",
    tags=["Meetings"],
    summary="Get meeting details",
    description="Retrieve detailed information about a specific meeting including transcription and generated tickets.",
    responses={
        200: {"description": "Meeting details retrieved successfully"},
        404: {"description": "Meeting not found"},
        401: {"description": "Authentication required"},
    }
)
async def get_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    meeting = await get_meeting_detail(
        db=db,
        meeting_id=meeting_id,
        user_id=current_user.id
    )
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting


@app.post(
    "/api/meetings/search",
    tags=["Meetings"],
    summary="Search meetings",
    description="Perform semantic search across meeting transcriptions to find relevant content.",
    responses={
        200: {"description": "Search results retrieved successfully"},
        401: {"description": "Authentication required"},
    }
)
async def search_meetings(
    query: str,
    project_key: Optional[str] = None,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    results = await semantic_search(
        db=db,
        query=query,
        user_id=current_user.id,
        project_key=project_key.upper() if project_key else None,
        limit=limit
    )
    return {"results": results}


@app.delete(
    "/api/meetings/{meeting_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Meetings"],
    summary="Delete meeting",
    description="Permanently delete a meeting and all its associated data.",
    responses={
        204: {"description": "Meeting deleted successfully"},
        404: {"description": "Meeting not found"},
        401: {"description": "Authentication required"},
    }
)
async def delete_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    await db.delete(meeting)
    await db.commit()


# ============ Static Files ============

app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")


@app.get("/")
async def serve_index():
    return FileResponse("../frontend/templates/index.html")


@app.get("/{path:path}")
async def serve_spa(path: str):
    if not path.startswith("api/"):
        return FileResponse("../frontend/templates/index.html")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
