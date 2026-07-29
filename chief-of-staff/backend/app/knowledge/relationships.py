from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.relationship import KnowledgeRelationship


def add_relationship(db: Session, *, organization_id: str, source: str, target: str, relation: str) -> tuple[KnowledgeRelationship, bool]:
    existing = (
        db.query(KnowledgeRelationship)
        .filter(
            KnowledgeRelationship.organization_id == organization_id,
            KnowledgeRelationship.source == source,
            KnowledgeRelationship.target == target,
            KnowledgeRelationship.relation == relation,
        )
        .first()
    )

    if existing is not None:
        return existing, False

    relationship = KnowledgeRelationship(
        organization_id=organization_id,
        source=source,
        target=target,
        relation=relation,
    )

    db.add(relationship)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(KnowledgeRelationship)
            .filter(
                KnowledgeRelationship.organization_id == organization_id,
                KnowledgeRelationship.source == source,
                KnowledgeRelationship.target == target,
                KnowledgeRelationship.relation == relation,
            )
            .one()
        )
        return existing, False

    db.refresh(relationship)
    return relationship, True


def list_relationships(db: Session, *, organization_id: str, limit: int = 200) -> list[KnowledgeRelationship]:
    return (
        db.query(KnowledgeRelationship)
        .filter(KnowledgeRelationship.organization_id == organization_id)
        .order_by(KnowledgeRelationship.created_at.desc())
        .limit(limit)
        .all()
    )


def relationships_for_entity(db: Session, entity_key: str, *, organization_id: str, limit: int = 200) -> list[KnowledgeRelationship]:
    return (
        db.query(KnowledgeRelationship)
        .filter(
            KnowledgeRelationship.organization_id == organization_id,
            or_(KnowledgeRelationship.source == entity_key, KnowledgeRelationship.target == entity_key),
        )
        .order_by(KnowledgeRelationship.created_at.desc())
        .limit(limit)
        .all()
    )


def relationship_count(db: Session, organization_id: str) -> int:
    return db.query(KnowledgeRelationship).filter(KnowledgeRelationship.organization_id == organization_id).count()
