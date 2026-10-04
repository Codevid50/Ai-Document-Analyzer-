import json
import os

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_service import (
    summarize_text,
    ask_question,
    AIServiceError,
    AIRateLimitError,
    AIAuthenticationError,
    AIMalformedResponseError,
    AINonJsonResponseError,
    AIModelUnavailableError,
)
from app.models import SummaryResponse, AskResponse
from app.pdf_service import extract_text, chunk_text
from app.auth import router as auth_router
from app.admin import router as admin_router
from app.db import (
    Document,
    Message,
    User,
    file_hash,
    get_db,
    get_or_create_document,
    get_recent_messages,
)
from app.visitors import get_visitor_user


app = FastAPI(
    title="AI PDF Summarizer"
)
app.include_router(auth_router)
app.include_router(admin_router)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


def _get_or_create_request_document(
    file: UploadFile | None,
    document_id: int | None,
    session: Session,
    user: User,
) -> tuple[Document, str]:
    if document_id is not None:
        document = session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user.id,
            )
        )
        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )
        return document, document.text

    if file is None:
        raise HTTPException(
            status_code=400,
            detail="A PDF file or document_id is required",
        )
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    try:
        data = file.file.read()
        sha256 = file_hash(data)
        file.file.seek(0)
        text = extract_text(file.file)
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="Failed to read the PDF file. It may be corrupted.",
        ) from error

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No extractable text found in this PDF",
        )

    document = get_or_create_document(
        session,
        user.id,
        file.filename or "",
        sha256,
        text,
    )
    return document, document.text


@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    user: User = Depends(get_visitor_user),
):

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    try:
        data = file.file.read()
        sha256 = file_hash(data)
        file.file.seek(0)
        text = extract_text(file.file)

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="Failed to read the PDF file. It may be corrupted.",
        ) from error

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No extractable text found in this PDF",
        )

    get_or_create_document(
        session,
        user.id,
        file.filename or "",
        sha256,
        text,
    )
    session.commit()

    return {
        "filename": file.filename,
        "text": text,
    }


@app.post(
    "/summarize",
    response_model=SummaryResponse,
)
def summarize_pdf(
    file: UploadFile | None = File(None),
    document_id: int | None = Form(None),
    session: Session = Depends(get_db),
    user: User = Depends(get_visitor_user),
):
    document, text = _get_or_create_request_document(
        file,
        document_id,
        session,
        user,
    )
    filename = (
        document.filename
        if document_id is not None or file is None
        else file.filename or document.filename
    )
    if document.summary_json is not None:
        summary = json.loads(document.summary_json)
        return {
            "document_id": document.id,
            "filename": filename,
            **summary,
        }

    chunks = chunk_text(text)

    try:
        summary = summarize_text(
            text,
            chunks,
        )

    except AIRateLimitError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except AIAuthenticationError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    except AIModelUnavailableError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except AIMalformedResponseError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except AINonJsonResponseError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except AIServiceError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from error

    document.summary_json = json.dumps(summary)
    session.commit()

    return {
        "document_id": document.id,
        "filename": filename,
        **summary,
    }


@app.post(
    "/ask",
    response_model=AskResponse,
)
def ask_pdf_question(
    file: UploadFile | None = File(None),
    document_id: int | None = Form(None),
    question: str = Form(""),
    session: Session = Depends(get_db),
    user: User = Depends(get_visitor_user),
):
    if not question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question must not be empty",
        )

    document, text = _get_or_create_request_document(
        file,
        document_id,
        session,
        user,
    )
    filename = (
        document.filename
        if document_id is not None or file is None
        else file.filename or document.filename
    )
    history = get_recent_messages(session, document.id, limit=8)

    try:
        answer = ask_question(text, question, history=history)

    except AIRateLimitError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except AIAuthenticationError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    except AIModelUnavailableError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except AIMalformedResponseError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except AINonJsonResponseError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except AIServiceError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from error

    session.add_all(
        [
            Message(
                document_id=document.id,
                role="user",
                content=question,
            ),
            Message(
                document_id=document.id,
                role="assistant",
                content=answer,
            ),
        ]
    )
    session.commit()

    return {
        "filename": filename,
        "question": question,
        "answer": answer,
    }


@app.get("/documents/{document_id}/messages")
def get_document_messages(
    document_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_visitor_user),
):
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user.id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return {
        "document_id": document.id,
        "filename": document.filename,
        "summary": (
            json.loads(document.summary_json)
            if document.summary_json is not None
            else None
        ),
        "messages": [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in document.messages
        ],
    }


@app.get("/documents")
def list_documents(
    session: Session = Depends(get_db),
    user: User = Depends(get_visitor_user),
):
    documents = session.scalars(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    ).all()
    return [
        {
            "id": document.id,
            "filename": document.filename,
            "created_at": document.created_at,
            "has_summary": document.summary_json is not None,
        }
        for document in documents
    ]


@app.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(get_visitor_user),
):
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user.id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    session.delete(document)
    session.commit()
    return Response(status_code=204)
