# ActionSync API Documentation

## Interactive Documentation

ActionSync provides comprehensive interactive API documentation through FastAPI's built-in tools:

### 🚀 Swagger UI
- **URL**: `/docs`
- **Features**: Interactive API testing, request/response examples, authentication support
- **Best for**: Testing endpoints and understanding API structure

### 📚 ReDoc
- **URL**: `/redoc` 
- **Features**: Clean documentation layout, detailed schema descriptions
- **Best for**: Reading comprehensive API documentation

### 📄 OpenAPI Specification
- **JSON**: `/openapi.json`
- **YAML**: Export using `python openapi_export.py`

## Authentication

Most endpoints require Bearer token authentication:

```bash
# Get token
curl -X POST "/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# Use token
curl -X GET "/api/auth/me" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Quick Start

1. **Register**: `POST /api/auth/register`
2. **Login**: `POST /api/auth/login` 
3. **Configure Jira**: `POST /api/jira/config`
4. **Add Project**: `POST /api/jira/projects`
5. **Process Meeting**: `POST /api/meetings/process`

## API Categories

- **Authentication**: User management and JWT tokens
- **Jira Configuration**: Integration settings
- **Projects**: Jira project management
- **Meetings**: Transcription processing and history
- **Kanban**: Board operations and tickets
- **AI Work**: Automated ticket processing
- **Processing**: Background task management
- **WebSocket**: Real-time updates

Visit `/docs` for complete interactive documentation!