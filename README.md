# ActionSync

Transform meeting transcriptions into Jira tickets automatically using Claude AI.

## Features

- **AI-Powered Meeting Processing**: Claude analyzes meeting transcriptions and intelligently creates, updates, and links Jira issues
- **Question & Answer Mode**: Ask questions about your Jira project with context from meetings and code
- **User Authentication**: Secure JWT-based authentication with bcrypt password hashing
- **Jira Integration**: Configure your Jira instance and manage multiple projects
- **GitLab Integration**: Optionally connect GitLab repositories to provide code context for ticket creation
- **Meeting History & Semantic Search** (Beta): Store processed meetings with vector embeddings for intelligent search
- **Real-time Updates**: WebSocket connection for live processing feedback
- **Per-Project Customization**: Custom instructions, GitLab repos, and embeddings settings per project

## Architecture

```
Frontend (Vanilla JavaScript SPA)
    ↓
FastAPI Backend (Python/Async)
    ↓
PostgreSQL Database (with pgvector)
    ↓
Claude AI (via Azure Anthropic API)
    ↓
Jira REST API + GitLab API
```

- **Backend**: FastAPI with async SQLAlchemy (PostgreSQL/SQLite)
- **Frontend**: Vanilla JavaScript SPA with modern dark theme
- **AI**: Claude via Azure Anthropic with MCP tools for Jira operations
- **Embeddings**: Azure OpenAI for semantic search (optional)
- **Auth**: JWT tokens with bcrypt password hashing

## Quick Start

### Using Docker Compose (Recommended)

1. Create a `.env` file in the root directory:
   ```env
   # Required
   SECRET_KEY=your-secure-secret-key
   AZURE_ANTHROPIC_ENDPOINT=your-azure-anthropic-endpoint
   AZURE_ANTHROPIC_API_KEY=your-azure-anthropic-api-key

   # Optional - for meeting history/semantic search
   AZURE_OPENAI_ENDPOINT=your-azure-openai-endpoint
   AZURE_OPENAI_API_KEY=your-azure-openai-api-key
   ```

2. Start the application:
   ```bash
   docker-compose up -d
   ```

3. Access at http://localhost:8080

### Manual Setup

1. Install Python dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Set environment variables (see [Environment Variables](#environment-variables))

3. Run the server:
   ```bash
   python server.py
   ```

## Configuration

### Jira Setup

1. Create an API token at https://id.atlassian.com/manage-profile/security/api-tokens
2. In the app Settings, enter:
   - Jira Base URL (e.g., `https://yourcompany.atlassian.net`)
   - Your Jira email
   - The API token you created

### GitLab Setup (Optional)

1. Create a Personal Access Token in GitLab with `read_repository` scope
2. In Settings, enter:
   - GitLab URL (e.g., `https://gitlab.com`)
   - Personal Access Token

### Adding Projects

In Settings, add Jira project keys (e.g., `PROJ`, `DEV`, `SUPPORT`) with optional configuration:
- **GitLab Projects**: Comma-separated repository paths to clone for code context
- **Custom Instructions**: Additional guidance for Claude when processing meetings
- **Embeddings Enabled**: Toggle meeting history storage for semantic search

## Usage

### Meeting Processing Mode

1. Go to Dashboard and select "Meeting" mode
2. Select a project
3. Paste your meeting transcription
4. Click "Process Meeting"
5. Watch Claude analyze and create/update tickets in real-time
6. View results with links to created tickets

### Question Mode

1. Go to Dashboard and select "Question" mode
2. Select a project
3. Ask a question about your project
4. Claude will search Jira, meeting history, and code (if configured) to provide answers

### Meeting History (Beta)

1. Go to History to view past processed meetings
2. Use search to find meetings by content
3. Click on a meeting to view details and summary

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | JWT signing secret (change in production) |
| `AZURE_ANTHROPIC_ENDPOINT` | Yes | Azure Anthropic API endpoint |
| `AZURE_ANTHROPIC_API_KEY` | Yes | Azure Anthropic API key |
| `AZURE_ANTHROPIC_MODEL` | No | Claude model (default: `claude-opus-4-5`) |
| `DATABASE_URL` | No | Database connection string (default: SQLite) |
| `AZURE_OPENAI_ENDPOINT` | No | Azure OpenAI endpoint (for embeddings) |
| `AZURE_OPENAI_API_KEY` | No | Azure OpenAI API key (for embeddings) |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | No | Embedding model (default: `text-embedding-3-small`) |

## API Endpoints

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Create account |
| `/api/auth/login` | POST | Login (returns JWT) |
| `/api/auth/me` | GET | Get current user |

### Jira Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jira/config` | GET | Get Jira config |
| `/api/jira/config` | POST | Create Jira config |
| `/api/jira/config` | PUT | Update Jira config |

### Projects

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jira/projects` | GET | List projects |
| `/api/jira/projects` | POST | Add project |
| `/api/jira/projects/{id}` | PUT | Update project settings |
| `/api/jira/projects/{id}` | DELETE | Remove project |

### Processing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/meetings/process` | POST | Process meeting transcription |
| `/api/jira/ask` | POST | Ask a question about the project |
| `/api/processing/status` | GET | Check processing status |
| `/api/processing/abort` | POST | Cancel current processing |

### Meeting History

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/meetings` | GET | List meetings (paginated) |
| `/api/meetings/{id}` | GET | Get meeting details |
| `/api/meetings/{id}` | DELETE | Delete meeting |
| `/api/meetings/search` | POST | Semantic search across meetings |

### Real-time

| Endpoint | Type | Description |
|----------|------|-------------|
| `/ws?token={jwt}` | WebSocket | Real-time processing updates |

## Deployment

### Docker

```bash
docker build -t actionsync .
docker run -p 8080:8080 --env-file .env actionsync
```

### OpenShift

Deployment manifests are provided in the `openshift/` directory:
- PostgreSQL StatefulSet with persistent storage
- Application Deployment with health checks
- Service and Route configuration
- Secrets management for credentials

## Tech Stack

- **Python 3.12** with FastAPI
- **PostgreSQL 16** with pgvector extension
- **Claude AI** via Azure Anthropic
- **Azure OpenAI** for embeddings
- **Vanilla JavaScript** SPA frontend
- **Docker** & **OpenShift** deployment support
