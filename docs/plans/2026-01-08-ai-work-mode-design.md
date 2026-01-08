# AI Work Mode Design

**Date:** 2026-01-08
**Status:** Approved

## Overview

Add a new "Work" mode that displays a Kanban board of Jira tickets. Users can pick a ticket and have Claude AI automatically implement it, push code to GitLab with a merge request, and update the Jira ticket.

## User Flow

1. User navigates to Work mode
2. Sees Kanban board with columns from Jira workflow (fetched dynamically)
3. Tickets filtered by custom JQL configured per project
4. User clicks ticket → sees details panel
5. User clicks "Start Work" → AI takes over
6. User sees streaming output (git commands, file edits, AI thinking)
7. On completion: MR created, Jira ticket updated with comment and link

## Technical Design

### Database Changes

Add one field to `JiraProject` model:

```python
kanban_jql = Column(String, nullable=True)  # e.g., "status != Done AND assignee = currentUser()"
```

### Backend API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jira/workflow/{project_key}` | GET | Get workflow statuses for Kanban columns |
| `/api/jira/kanban/{project_key}` | GET | Get tickets matching project's `kanban_jql` |
| `/api/jira/ticket/{issue_key}` | GET | Get full ticket details |
| `/api/work/start` | POST | Start AI work on a ticket |

#### POST /api/work/start

**Request:**
```json
{
  "project_id": 1,
  "issue_key": "PROJ-123"
}
```

**Response:** Streams via WebSocket (same as meeting processing)

### Pre-work Setup (Backend)

Before invoking Claude:

1. Fetch ticket details from Jira (summary, description, comments)
2. Clone all repos from `gitlab_projects` to `/tmp/work/{issue_key}/`
3. Pass context to Claude

### Claude's Responsibilities

Claude uses existing tools (Bash, Read, Write, Edit, Glob, Grep, Jira MCP):

1. Transition ticket to "In Progress"
2. Analyze ticket content
3. Decide which repo(s) to modify
4. Create branch (AI-generated descriptive name)
5. Implement the changes
6. Commit and push with MR creation:
   ```bash
   git push -o merge_request.create -o merge_request.target=main origin branch-name
   ```
7. Add comment to Jira ticket with MR link
8. Transition ticket to appropriate status (e.g., "Code Review")

### Error Handling

- If AI fails at any point: abort, cleanup temp directory, notify user
- No partial code pushed to GitLab

### Frontend Changes

**Mode Selector:**
- Add "Work" tab alongside "Meeting" and "Question"

**Kanban View:**
- Columns from Jira workflow statuses (dynamic)
- Cards: ticket key, summary, assignee, priority
- Click card → detail panel

**Ticket Detail Panel:**
- Full ticket info (summary, description, comments)
- "Start Work" button

**Work Progress View:**
- Streaming console (reuse existing WebSocket UI)
- Final summary with MR link

**Settings:**
- Add "Kanban JQL Filter" field per project

## Components Summary

| Component | Changes |
|-----------|---------|
| Database | Add `kanban_jql` to `JiraProject` |
| Backend | 4 new endpoints |
| Backend | Work processor (clone + invoke Claude) |
| Frontend | Kanban board view |
| Frontend | Ticket detail panel |
| Frontend | Settings field for JQL |

## What We're NOT Building

- No new Claude tools (uses existing capabilities)
- No work session persistence (evidence is in Jira/GitLab)
- No manual drag-drop status transitions (could add later)
