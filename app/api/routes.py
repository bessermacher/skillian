"""API routes."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SessionInfo,
    SessionListResponse,
    SkillInfo,
    SkillsResponse,
    ToolCall,
)
from app.api.sessions import SessionStore
from app.config import get_settings
from app.core import Agent
from app.dependencies import (
    get_agent,
    get_llm_provider,
    get_rag_manager,
    get_session_store,
    get_skill_registry,
)
from app.rag import RAGManager

router = APIRouter()


# Health & Info


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
)
async def health_check() -> HealthResponse:
    """Check application health status."""
    settings = get_settings()
    provider = get_llm_provider()
    registry = get_skill_registry()

    try:
        rag_manager = get_rag_manager()
        doc_count = rag_manager.document_count
    except Exception:
        doc_count = 0

    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        environment=settings.env,
        llm_provider=provider.provider_name,
        llm_model=provider.model_name,
        connector="none",
        connector_healthy=True,
        skills_count=registry.skill_count,
        tools_count=registry.tool_count,
        knowledge_documents=doc_count,
    )


@router.get(
    "/skills",
    response_model=SkillsResponse,
    tags=["Info"],
)
async def list_skills() -> SkillsResponse:
    """List all registered skills and their tools."""
    registry = get_skill_registry()
    skills = []
    for skill in registry.get_all_skills():
        skills.append(
            SkillInfo(
                name=skill.name,
                description=skill.description,
                tools=[
                    {"name": t.name, "description": t.description}
                    for t in skill.tools
                ],
                knowledge_paths=skill.knowledge_paths,
            )
        )
    return SkillsResponse(skills=skills)


# Chat


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}},
    tags=["Chat"],
)
async def chat(
    request: ChatRequest,
    agent: Agent = Depends(get_agent),
) -> ChatResponse:
    """Process a chat message.

    Creates a new conversation for each request.
    For persistent conversations, use session endpoints.
    """
    try:
        result = await agent.process(request.message)
        return ChatResponse(
            response=result.content,
            tool_calls=[
                ToolCall(
                    tool=tc["tool"],
                    args=tc["args"],
                    result=tc["result"],
                )
                for tc in result.tool_calls_made
            ],
            finished=result.finished,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Sessions


@router.post(
    "/sessions",
    response_model=ChatResponse,
    tags=["Sessions"],
)
async def create_session_and_chat(
    request: ChatRequest,
    session_store: SessionStore = Depends(get_session_store),
) -> ChatResponse:
    """Create a new session and process the first message."""
    session = await session_store.create()

    result = await session.agent.process(request.message)
    session.increment_messages()
    await session_store.update(session)

    return ChatResponse(
        response=result.content,
        tool_calls=[
            ToolCall(tool=tc["tool"], args=tc["args"], result=tc["result"])
            for tc in result.tool_calls_made
        ],
        session_id=session.session_id,
        finished=result.finished,
    )


@router.post(
    "/sessions/{session_id}/chat",
    response_model=ChatResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["Sessions"],
)
async def session_chat(
    session_id: str,
    request: ChatRequest,
    session_store: SessionStore = Depends(get_session_store),
) -> ChatResponse:
    """Continue a conversation in an existing session."""
    session = await session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await session.agent.process(request.message)
    session.increment_messages()
    await session_store.update(session)

    return ChatResponse(
        response=result.content,
        tool_calls=[
            ToolCall(tool=tc["tool"], args=tc["args"], result=tc["result"])
            for tc in result.tool_calls_made
        ],
        session_id=session.session_id,
        finished=result.finished,
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    tags=["Sessions"],
)
async def list_sessions(
    session_store: SessionStore = Depends(get_session_store),
) -> SessionListResponse:
    """List all active sessions."""
    sessions = await session_store.list_all()
    return SessionListResponse(
        sessions=[
            SessionInfo(
                session_id=s.session_id,
                message_count=s.message_count,
                created_at=s.created_at.isoformat(),
            )
            for s in sessions
        ]
    )


@router.delete(
    "/sessions/{session_id}",
    tags=["Sessions"],
)
async def delete_session(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
) -> dict:
    """Delete a session."""
    deleted = await session_store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


# Knowledge


@router.post(
    "/knowledge/ingest",
    response_model=IngestResponse,
    tags=["Knowledge"],
)
async def ingest_knowledge(
    rag_manager: RAGManager = Depends(get_rag_manager),
) -> IngestResponse:
    """Ingest knowledge from all skill directories."""
    results = rag_manager.ingest_all_skills()
    total = sum(results.values())
    return IngestResponse(
        status="success",
        chunks_ingested=total,
        by_skill=results,
    )


@router.post(
    "/knowledge/search",
    response_model=SearchResponse,
    tags=["Knowledge"],
)
async def search_knowledge(
    request: SearchRequest,
    rag_manager: RAGManager = Depends(get_rag_manager),
) -> SearchResponse:
    """Search the knowledge base."""
    docs = rag_manager.store.search_with_scores(request.query, k=request.k)

    results = [
        SearchResult(
            content=doc.page_content,
            source=doc.metadata.get("filename", "Unknown"),
            skill=doc.metadata.get("skill", "Unknown"),
            score=score,
        )
        for doc, score in docs
    ]

    return SearchResponse(
        results=results,
        query=request.query,
        count=len(results),
    )
