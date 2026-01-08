"""
Embedding Service

Handles text chunking, embedding generation, and semantic search.
Uses Azure OpenAI for embeddings and LangChain for text splitting.
"""

import json
from typing import List, Optional
from openai import AsyncAzureOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import get_settings
from models import Meeting, MeetingChunk, EMBEDDING_DIM

settings = get_settings()

# Chunk configuration
CHUNK_SIZE = 1000  # Characters per chunk (larger for better context)
CHUNK_OVERLAP = 200  # Overlap between chunks

# LangChain text splitter with smart separators
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    is_separator_regex=False,
    separators=[
        "\n\n",  # Paragraph breaks
        "\n",    # Line breaks
        ". ",    # Sentences
        "? ",    # Questions
        "! ",    # Exclamations
        "; ",    # Semi-colons
        ", ",    # Commas
        " ",     # Words
        ""       # Characters
    ]
)


def chunk_text(content: str) -> List[str]:
    """
    Split text into overlapping chunks using LangChain's RecursiveCharacterTextSplitter.
    This provides better semantic boundaries than simple character splitting.
    """
    if not content:
        return []

    chunks = text_splitter.split_text(content)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


async def get_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding for a single text using Azure OpenAI.
    """
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        print("Azure OpenAI not configured, skipping embedding generation")
        return None

    try:
        client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version="2024-02-01"
        )

        response = await client.embeddings.create(
            input=text,
            model=settings.azure_openai_embedding_deployment
        )

        return response.data[0].embedding

    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None


async def get_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in batch.
    """
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        print("Azure OpenAI not configured, skipping embedding generation")
        return [None] * len(texts)

    try:
        client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version="2024-02-01"
        )

        response = await client.embeddings.create(
            input=texts,
            model=settings.azure_openai_embedding_deployment
        )

        # Sort by index to maintain order
        embeddings = [None] * len(texts)
        for item in response.data:
            embeddings[item.index] = item.embedding

        return embeddings

    except Exception as e:
        print(f"Error generating embeddings batch: {e}")
        return [None] * len(texts)


async def store_meeting_with_embeddings(
    db: AsyncSession,
    user_id: int,
    project_key: str,
    transcription: str,
    summary: Optional[str] = None,
    tickets_created: Optional[List[str]] = None,
    title: Optional[str] = None
) -> Meeting:
    """
    Store a meeting and its chunks with embeddings.
    """
    # Create meeting record
    meeting = Meeting(
        user_id=user_id,
        project_key=project_key,
        title=title or f"Meeting - {project_key}",
        transcription=transcription,
        summary=summary,
        tickets_created=json.dumps(tickets_created) if tickets_created else None
    )
    db.add(meeting)
    await db.flush()  # Get the meeting ID

    # Chunk the transcription
    chunks = chunk_text(transcription)
    print(f"[Embedding] Created {len(chunks)} chunks for meeting {meeting.id}")

    # Generate embeddings for all chunks
    embeddings = await get_embeddings_batch(chunks)

    # Create chunk records
    for i, (chunk_text_content, embedding) in enumerate(zip(chunks, embeddings)):
        chunk = MeetingChunk(
            meeting_id=meeting.id,
            chunk_index=i,
            content=chunk_text_content,
            embedding=embedding
        )
        db.add(chunk)

    await db.commit()
    await db.refresh(meeting)

    print(f"[Embedding] Stored meeting {meeting.id} with {len(chunks)} chunks")
    return meeting


async def semantic_search(
    db: AsyncSession,
    query: str,
    user_id: int,
    project_key: Optional[str] = None,
    limit: int = 10
) -> List[dict]:
    """
    Perform semantic search on meeting chunks.
    Returns chunks ordered by similarity.
    """
    # Generate embedding for query
    query_embedding = await get_embedding(query)

    if not query_embedding:
        print("[Embedding] No query embedding, falling back to text search")
        return await text_search(db, query, user_id, project_key, limit)

    # Build the query with cosine similarity
    # pgvector uses <=> for cosine distance (1 - similarity)
    embedding_str = f"[{','.join(map(str, query_embedding))}]"

    if project_key:
        sql = text("""
            SELECT mc.id, mc.content, mc.chunk_index, m.id as meeting_id, m.title,
                   m.project_key, m.created_at,
                   1 - (mc.embedding <=> CAST(:embedding AS vector)) as similarity
            FROM meeting_chunks mc
            JOIN meetings m ON mc.meeting_id = m.id
            WHERE m.user_id = :user_id AND m.project_key = :project_key
            AND mc.embedding IS NOT NULL
            ORDER BY mc.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)
        result = await db.execute(sql, {
            "embedding": embedding_str,
            "user_id": user_id,
            "project_key": project_key,
            "limit": limit
        })
    else:
        sql = text("""
            SELECT mc.id, mc.content, mc.chunk_index, m.id as meeting_id, m.title,
                   m.project_key, m.created_at,
                   1 - (mc.embedding <=> CAST(:embedding AS vector)) as similarity
            FROM meeting_chunks mc
            JOIN meetings m ON mc.meeting_id = m.id
            WHERE m.user_id = :user_id
            AND mc.embedding IS NOT NULL
            ORDER BY mc.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)
        result = await db.execute(sql, {
            "embedding": embedding_str,
            "user_id": user_id,
            "limit": limit
        })

    rows = result.fetchall()

    return [
        {
            "chunk_id": row.id,
            "content": row.content,
            "chunk_index": row.chunk_index,
            "meeting_id": row.meeting_id,
            "meeting_title": row.title,
            "project_key": row.project_key,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "similarity": float(row.similarity) if row.similarity else 0
        }
        for row in rows
    ]


async def text_search(
    db: AsyncSession,
    query: str,
    user_id: int,
    project_key: Optional[str] = None,
    limit: int = 10
) -> List[dict]:
    """
    Fallback text search using ILIKE.
    """
    search_pattern = f"%{query}%"

    if project_key:
        sql = text("""
            SELECT mc.id, mc.content, mc.chunk_index, m.id as meeting_id, m.title,
                   m.project_key, m.created_at
            FROM meeting_chunks mc
            JOIN meetings m ON mc.meeting_id = m.id
            WHERE m.user_id = :user_id AND m.project_key = :project_key
            AND mc.content ILIKE :pattern
            ORDER BY m.created_at DESC
            LIMIT :limit
        """)
        result = await db.execute(sql, {
            "user_id": user_id,
            "project_key": project_key,
            "pattern": search_pattern,
            "limit": limit
        })
    else:
        sql = text("""
            SELECT mc.id, mc.content, mc.chunk_index, m.id as meeting_id, m.title,
                   m.project_key, m.created_at
            FROM meeting_chunks mc
            JOIN meetings m ON mc.meeting_id = m.id
            WHERE m.user_id = :user_id
            AND mc.content ILIKE :pattern
            ORDER BY m.created_at DESC
            LIMIT :limit
        """)
        result = await db.execute(sql, {
            "user_id": user_id,
            "pattern": search_pattern,
            "limit": limit
        })

    rows = result.fetchall()

    return [
        {
            "chunk_id": row.id,
            "content": row.content,
            "chunk_index": row.chunk_index,
            "meeting_id": row.meeting_id,
            "meeting_title": row.title,
            "project_key": row.project_key,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "similarity": 0.5  # Placeholder for text search
        }
        for row in rows
    ]


async def get_meetings(
    db: AsyncSession,
    user_id: int,
    project_key: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[dict]:
    """
    Get meetings for a user, optionally filtered by project.
    """
    if project_key:
        sql = text("""
            SELECT id, project_key, title, summary, tickets_created, created_at,
                   (SELECT COUNT(*) FROM meeting_chunks WHERE meeting_id = meetings.id) as chunk_count
            FROM meetings
            WHERE user_id = :user_id AND project_key = :project_key
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        result = await db.execute(sql, {
            "user_id": user_id,
            "project_key": project_key,
            "limit": limit,
            "offset": offset
        })
    else:
        sql = text("""
            SELECT id, project_key, title, summary, tickets_created, created_at,
                   (SELECT COUNT(*) FROM meeting_chunks WHERE meeting_id = meetings.id) as chunk_count
            FROM meetings
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        result = await db.execute(sql, {
            "user_id": user_id,
            "limit": limit,
            "offset": offset
        })

    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "project_key": row.project_key,
            "title": row.title,
            "summary": row.summary,
            "tickets_created": json.loads(row.tickets_created) if row.tickets_created else [],
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "chunk_count": row.chunk_count
        }
        for row in rows
    ]


async def get_meeting_detail(
    db: AsyncSession,
    meeting_id: int,
    user_id: int
) -> Optional[dict]:
    """
    Get full meeting details including transcription.
    """
    sql = text("""
        SELECT id, project_key, title, transcription, summary, tickets_created, created_at
        FROM meetings
        WHERE id = :meeting_id AND user_id = :user_id
    """)
    result = await db.execute(sql, {"meeting_id": meeting_id, "user_id": user_id})
    row = result.fetchone()

    if not row:
        return None

    return {
        "id": row.id,
        "project_key": row.project_key,
        "title": row.title,
        "transcription": row.transcription,
        "summary": row.summary,
        "tickets_created": json.loads(row.tickets_created) if row.tickets_created else [],
        "created_at": row.created_at.isoformat() if row.created_at else None
    }
