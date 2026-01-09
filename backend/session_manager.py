"""
Session Manager for Claude Agent SDK

Maintains Claude SDK client sessions to support multi-turn conversations.
"""

import asyncio
from typing import Dict, Optional, Any, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import uuid

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions


@dataclass
class Session:
    """A Claude SDK session with conversation context."""
    session_id: str
    user_id: int
    client: ClaudeSDKClient
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    is_processing: bool = False


class SessionManager:
    """Manages Claude SDK sessions for multi-turn conversations."""

    def __init__(self, session_timeout_minutes: int = 30):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[int, str] = {}  # user_id -> session_id
        self._session_timeout = timedelta(minutes=session_timeout_minutes)
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop the cleanup task and close all sessions."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all active sessions
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)

    async def _cleanup_loop(self):
        """Periodically clean up expired sessions."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            await self._cleanup_expired()

    async def _cleanup_expired(self):
        """Remove sessions that have been inactive for too long."""
        now = datetime.utcnow()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_activity > self._session_timeout
            and not session.is_processing
        ]
        for session_id in expired:
            print(f"[SessionManager] Cleaning up expired session: {session_id}")
            await self.close_session(session_id)

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session:
            session.last_activity = datetime.utcnow()
        return session

    def get_user_session(self, user_id: int) -> Optional[Session]:
        """Get the active session for a user."""
        session_id = self._user_sessions.get(user_id)
        if session_id:
            return self.get_session(session_id)
        return None

    async def create_session(
        self,
        user_id: int,
        options: ClaudeAgentOptions
    ) -> Session:
        """Create a new session for a user, closing any existing session."""
        # Close existing session for this user
        existing_session_id = self._user_sessions.get(user_id)
        if existing_session_id:
            await self.close_session(existing_session_id)

        # Create new session
        session_id = str(uuid.uuid4())
        client = ClaudeSDKClient(options=options)

        # Enter the async context manager
        await client.__aenter__()

        session = Session(
            session_id=session_id,
            user_id=user_id,
            client=client
        )

        self._sessions[session_id] = session
        self._user_sessions[user_id] = session_id

        print(f"[SessionManager] Created session {session_id} for user {user_id}")
        return session

    async def close_session(self, session_id: str):
        """Close and remove a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            # Remove user mapping
            if self._user_sessions.get(session.user_id) == session_id:
                del self._user_sessions[session.user_id]

            # Close the client
            try:
                await session.client.__aexit__(None, None, None)
            except Exception as e:
                print(f"[SessionManager] Error closing session {session_id}: {e}")

            print(f"[SessionManager] Closed session {session_id}")

    async def close_user_session(self, user_id: int):
        """Close the session for a specific user."""
        session_id = self._user_sessions.get(user_id)
        if session_id:
            await self.close_session(session_id)


# Global session manager instance
session_manager = SessionManager()
