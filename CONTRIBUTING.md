# Contributing to ActionSync

Thanks for your interest in contributing to ActionSync! This document provides guidelines for contributing.

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 16 with pgvector extension (or use SQLite for development)
- Azure Anthropic API access (for Claude)
- Optional: Azure OpenAI API access (for embeddings)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/action-sync.git
   cd action-sync
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run the development server**
   ```bash
   python server.py
   ```

6. **Access the app** at http://localhost:8080

## How to Contribute

### Reporting Bugs

- Check existing issues first to avoid duplicates
- Use the bug report template
- Include steps to reproduce, expected vs actual behavior
- Include relevant logs or screenshots

### Suggesting Features

- Use the feature request template
- Explain the use case and why it would be valuable
- Be open to discussion about implementation approaches

### Submitting Pull Requests

1. **Fork the repository** and create a branch from `master`
2. **Make your changes** with clear, descriptive commits
3. **Test your changes** thoroughly
4. **Update documentation** if needed
5. **Submit a PR** with a clear description of the changes

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add comments for complex logic
- Keep functions focused and reasonably sized

### Commit Messages

- Use clear, descriptive commit messages
- Start with a verb (Add, Fix, Update, Remove, etc.)
- Reference issue numbers when applicable (e.g., "Fix #123: Handle empty transcriptions")

## Project Structure

```
action-sync/
├── backend/
│   ├── server.py          # FastAPI application and routes
│   ├── models.py          # SQLAlchemy database models
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── auth.py            # Authentication utilities
│   ├── config.py          # Configuration management
│   ├── database.py        # Database connection setup
│   ├── meeting_processor.py   # Claude AI meeting processing
│   ├── jira_tools.py      # Jira API integration
│   ├── gitlab_tools.py    # GitLab API integration
│   └── embedding_service.py   # Vector embeddings for search
├── frontend/
│   ├── static/            # CSS and JavaScript
│   └── templates/         # HTML templates
├── openshift/             # OpenShift deployment configs
└── docker-compose.yml     # Local development setup
```

## Questions?

Feel free to open an issue for any questions about contributing.
