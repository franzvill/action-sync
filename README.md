# ActionSync

Transform meeting transcriptions into Jira tickets automatically using Claude AI.

<img width="3384" height="1910" alt="image" src="https://github.com/user-attachments/assets/a380985d-3fe5-431f-a170-5604e8960988" />

<img width="3394" height="1926" alt="image" src="https://github.com/user-attachments/assets/4301f4bb-ac17-4214-b463-0268d836af09" />


## Features

- **Meeting Mode**: Paste a meeting transcript. Claude analyzes it, checks your GitLab repos for technical context, and creates Jira tickets with relevant files, components, acceptance criteria, and links to related issues.
- **Ask Mode**: Ask questions about your project in natural language. Claude searches across Jira tickets, past meetings, and your codebase to find answers.
- **Work Mode**: Point Claude at a Jira ticket. It clones the relevant repos, reads the ticket and codebase, and works on the implementation.
- **GitLab Integration**: Connect GitLab repositories to provide code context for ticket creation and AI work.
- **Meeting History & Semantic Search**: Store processed meetings with vector embeddings for intelligent search.
- **Real-time Updates**: WebSocket connection for live processing feedback.
- **Per-Project Customization**: Custom instructions, GitLab repos, and settings per project.
- **Flexible API Support**: Works with direct Anthropic/OpenAI APIs or Azure-hosted versions - no Azure subscription required!

## Architecture

```
Frontend (Vanilla JavaScript SPA)
    ↓
FastAPI Backend (Python/Async)
    ↓
PostgreSQL Database (with pgvector)
    ↓
Claude AI (Anthropic or Azure Anthropic API)
OpenAI Embeddings (OpenAI or Azure OpenAI API)
    ↓
Jira REST API + GitLab API
```

- **Backend**: FastAPI with async SQLAlchemy (PostgreSQL/SQLite)
- **Frontend**: Vanilla JavaScript SPA with modern dark theme
- **AI**: Claude via Anthropic API (direct or Azure) with MCP tools for Jira operations
- **Embeddings**: OpenAI API (direct or Azure) for semantic search (optional)
- **Auth**: JWT tokens with bcrypt password hashing

## Quick Start

### Using Docker Compose (Recommended)

1. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

   Required variables:
   - `POSTGRES_PASSWORD` - Database password
   - `SECRET_KEY` - JWT signing secret
   - `LLM_PROVIDER` - Choose `anthropic` or `azure_anthropic`
   
   **For direct Anthropic API** (LLM_PROVIDER=anthropic):
   - `ANTHROPIC_API_KEY` - Your Anthropic API key
   
   **For Azure Anthropic** (LLM_PROVIDER=azure_anthropic):
   - `AZURE_ANTHROPIC_ENDPOINT` - Azure Anthropic API endpoint
   - `AZURE_ANTHROPIC_API_KEY` - Azure Anthropic API key

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

### Ask Mode

1. Go to Dashboard and select "Ask" mode
2. Select a project
3. Ask a question about your project
4. Claude searches Jira, meeting history, and code to provide answers

### Work Mode

1. Go to Dashboard and select "Work" mode
2. Select a project
3. Enter a Jira ticket key (e.g., `PROJ-123`)
4. Claude clones the configured GitLab repos, reads the ticket, and starts working
5. Watch progress in real-time as Claude analyzes code and implements changes

### Meeting History

1. Go to History to view past processed meetings
2. Use search to find meetings by content
3. Click on a meeting to view details and summary

## Environment Variables

### Core Settings

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | JWT signing secret (change in production) |
| `DATABASE_URL` | No | Database connection string (default: SQLite) |

### LLM Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | No | LLM provider: `anthropic` or `azure_anthropic` (default: `azure_anthropic`) |

**For Direct Anthropic (LLM_PROVIDER=anthropic):**

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key from api.anthropic.com |
| `ANTHROPIC_MODEL` | No | Claude model (default: `claude-opus-4-20250514`) |

**For Azure Anthropic (LLM_PROVIDER=azure_anthropic):**

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_ANTHROPIC_ENDPOINT` | Yes* | Azure Anthropic API endpoint |
| `AZURE_ANTHROPIC_API_KEY` | Yes* | Azure Anthropic API key |
| `AZURE_ANTHROPIC_MODEL` | No | Claude model (default: `claude-opus-4-5`) |

### Embedding Configuration (Optional - for semantic search)

| Variable | Required | Description |
|----------|----------|-------------|
| `EMBEDDING_PROVIDER` | No | Embedding provider: `openai` or `azure_openai` (default: `azure_openai`) |

**For Direct OpenAI (EMBEDDING_PROVIDER=openai):**

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key from platform.openai.com |
| `OPENAI_EMBEDDING_MODEL` | No | Embedding model (default: `text-embedding-3-small`) |

**For Azure OpenAI (EMBEDDING_PROVIDER=azure_openai):**

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes* | Azure OpenAI endpoint (for embeddings) |
| `AZURE_OPENAI_API_KEY` | Yes* | Azure OpenAI API key (for embeddings) |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | No | Embedding deployment name (default: `text-embedding-3-small`) |

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
| `/api/work/start` | POST | Start working on a Jira ticket |
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

## Tech Stack

- **Python 3.12** with FastAPI
- **PostgreSQL 16** with pgvector extension
- **Claude AI** via Azure Anthropic
- **Azure OpenAI** for embeddings
- **Vanilla JavaScript** SPA frontend
- **Docker** deployment support
