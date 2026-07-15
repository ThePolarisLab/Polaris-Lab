from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class MemoryType(str, Enum):
    NOTE="note"; MEETING="meeting"; DECISION="decision"; LESSON="lesson"; PROJECT="project"; CUSTOMER="customer"; OPERATIONAL="operational"
class DecisionStatus(str, Enum):
    PROPOSED="proposed"; APPROVED="approved"; SUPERSEDED="superseded"; REVERSED="reversed"
class KnowledgeType(str, Enum):
    FOUNDATION_PRINCIPLE="foundation_principle"
    CONSTITUTION="constitution"
    VISION="vision"
    MISSION="mission"
    BUILDER_STORY="builder_story"
    LESSON_LEARNED="lesson_learned"
    DECISION="decision"
    RESEARCH="research"
    PROJECT="project"
    MEETING="meeting"
    CONVERSATION="conversation"
    EXTERNAL_KNOWLEDGE="external_knowledge"
    ORGANIZATIONAL_MEMORY="organizational_memory"
class TruthStatus(str, Enum):
    ASSERTED="asserted"; VERIFIED="verified"; DISPUTED="disputed"; SUPERSEDED="superseded"
class Visibility(str, Enum):
    PRIVATE="private"; ORGANIZATION="organization"; PUBLIC="public"

class MemoryCreate(BaseModel):
    title:str=Field(min_length=1,max_length=200); content:str=Field(min_length=1); memory_type:MemoryType=MemoryType.NOTE
    source:str=Field(default="builder",min_length=1,max_length=100); importance:int=Field(default=3,ge=1,le=5); occurred_at:datetime=Field(default_factory=datetime.utcnow)
class MemoryRead(MemoryCreate):
    id:int; created_at:datetime
class DecisionCreate(BaseModel):
    title:str=Field(min_length=1,max_length=200); decision:str=Field(min_length=1); rationale:str=Field(min_length=1)
    status:DecisionStatus=DecisionStatus.APPROVED; decided_at:datetime=Field(default_factory=datetime.utcnow)
class DecisionRead(DecisionCreate):
    id:int; created_at:datetime
class KnowledgeCreate(BaseModel):
    title:str=Field(min_length=1,max_length=240); content:str=Field(min_length=1); knowledge_type:KnowledgeType
    author:str=Field(default="builder",min_length=1,max_length=120); organization:str|None=None
    importance:int=Field(default=3,ge=1,le=5); confidence:float=Field(default=1.0,ge=0,le=1)
    truth_status:TruthStatus=TruthStatus.ASSERTED; source:str=Field(default="builder",min_length=1,max_length=200)
    source_memory_id:int|None=None; visibility:Visibility=Visibility.PRIVATE
class KnowledgeRead(KnowledgeCreate):
    id:int; version:int; created_at:datetime; updated_at:datetime
class RelationshipCreate(BaseModel):
    source_knowledge_id:int; target_knowledge_id:int; relationship_type:str=Field(min_length=1,max_length=100)
    evidence:str|None=None; confidence:float=Field(default=1.0,ge=0,le=1)
class RelationshipRead(RelationshipCreate):
    id:int; created_at:datetime
class TimelineItem(BaseModel):
    item_type:str; id:int; title:str; summary:str; timestamp:datetime; importance:int|None=None; status:str|None=None
class Briefing(BaseModel):
    date:str; headline:str; priorities:list[TimelineItem]; recent_decisions:list[DecisionRead]
    featured_knowledge:list[KnowledgeRead]; memory_count:int; decision_count:int; knowledge_count:int
