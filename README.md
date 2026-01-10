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

1. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

   Required variables:
   - `POSTGRES_PASSWORD` - Database password
   - `SECRET_KEY` - JWT signing secret
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

### ServiceNow Setup (Optional)

ServiceNow integration enables automatic creation and management of ServiceNow tickets based on repository events.

1. Create a ServiceNow user account with appropriate permissions
2. In the app Settings, configure ServiceNow:
   - Instance URL (e.g., `https://dev123456.service-now.com`)
   - Username
   - Password
3. Use the "Test Connection" button to verify your configuration

**Supported Features:**
- Create incidents with customizable urgency and impact levels
- Create change requests for deployment tracking
- Update existing tickets with work notes
- Search and query incidents
- Close incidents with resolution notes

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
