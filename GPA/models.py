from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, JSON, LargeBinary, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    policy_type = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    version = Column(String(50), nullable=True)

    file_data = Column(LargeBinary, nullable=True)
    file_path = Column(String(500), nullable=True)

    source = Column(String(255), nullable=True, default="local_dev")
    processing_status = Column(String(50), nullable=False, default="NEW")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chunks = relationship("PolicyChunk", back_populates="document", cascade="all, delete-orphan")
    rules = relationship("PolicyRule", back_populates="document", cascade="all, delete-orphan")


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("policy_documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    section_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("PolicyDocument", back_populates="chunks")


class PolicyRule(Base):
    __tablename__ = "policy_rules"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_id", "subject", "operator", "value", "action",
            name="uq_policy_rule"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("policy_documents.id"), nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("policy_chunks.id"), nullable=False, index=True)

    rule_type = Column(String(100), nullable=False)
    subject = Column(String(255), nullable=True)
    operator = Column(String(50), nullable=True)
    value = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False)
    condition_text = Column(Text, nullable=False)
    confidence = Column(Float, default=0.5)

    approver = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("PolicyDocument", back_populates="rules")


class IncomingTask(Base):
    __tablename__ = "incoming_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), nullable=False, unique=True, index=True)
    task_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GovernanceDecision(Base):
    __tablename__ = "governance_decisions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), nullable=False, index=True)
    decision = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    requires_approval = Column(Boolean, default=False)
    next_agent = Column(String(100), nullable=False)
    matched_rule_ids = Column(JSON, nullable=True)
    matched_chunk_ids = Column(JSON, nullable=True)
    decision_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())