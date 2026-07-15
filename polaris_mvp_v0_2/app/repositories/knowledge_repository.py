from __future__ import annotations
from datetime import datetime
from app.core.database import get_connection
from app.models.schemas import KnowledgeCreate, KnowledgeRead, RelationshipCreate, RelationshipRead
class KnowledgeRepository:
    def create(self,item:KnowledgeCreate)->KnowledgeRead:
        now=datetime.utcnow()
        with get_connection() as c:
            cur=c.execute("""INSERT INTO knowledge(title,content,knowledge_type,author,organization,importance,confidence,truth_status,source,source_memory_id,version,visibility,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(item.title,item.content,item.knowledge_type.value,item.author,item.organization,item.importance,item.confidence,item.truth_status.value,item.source,item.source_memory_id,1,item.visibility.value,now.isoformat(),now.isoformat()))
            kid=int(cur.lastrowid)
        return self.get(kid)
    def get(self,knowledge_id:int)->KnowledgeRead:
        with get_connection() as c: row=c.execute("SELECT * FROM knowledge WHERE id=?",(knowledge_id,)).fetchone()
        if row is None: raise KeyError(knowledge_id)
        return self._to_model(row)
    def list(self,query:str|None=None,knowledge_type:str|None=None,limit:int=100)->list[KnowledgeRead]:
        where=[]; params=[]
        if query: where.append("(title LIKE ? OR content LIKE ?)"); term=f"%{query}%"; params += [term,term]
        if knowledge_type: where.append("knowledge_type=?"); params.append(knowledge_type)
        sql="SELECT * FROM knowledge" + ((" WHERE "+" AND ".join(where)) if where else "") + " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        with get_connection() as c: rows=c.execute(sql,params).fetchall()
        return [self._to_model(r) for r in rows]
    def count(self)->int:
        with get_connection() as c: return int(c.execute("SELECT COUNT(*) count FROM knowledge").fetchone()["count"])
    def create_relationship(self,item:RelationshipCreate)->RelationshipRead:
        now=datetime.utcnow()
        self.get(item.source_knowledge_id); self.get(item.target_knowledge_id)
        with get_connection() as c:
            cur=c.execute("INSERT INTO knowledge_relationships(source_knowledge_id,target_knowledge_id,relationship_type,evidence,confidence,created_at) VALUES(?,?,?,?,?,?)",(item.source_knowledge_id,item.target_knowledge_id,item.relationship_type,item.evidence,item.confidence,now.isoformat()))
            rid=int(cur.lastrowid)
        return self.get_relationship(rid)
    def get_relationship(self,relationship_id:int)->RelationshipRead:
        with get_connection() as c: row=c.execute("SELECT * FROM knowledge_relationships WHERE id=?",(relationship_id,)).fetchone()
        if row is None: raise KeyError(relationship_id)
        return RelationshipRead(id=row["id"],source_knowledge_id=row["source_knowledge_id"],target_knowledge_id=row["target_knowledge_id"],relationship_type=row["relationship_type"],evidence=row["evidence"],confidence=row["confidence"],created_at=datetime.fromisoformat(row["created_at"]))
    def relationships_for(self,knowledge_id:int)->list[RelationshipRead]:
        self.get(knowledge_id)
        with get_connection() as c: rows=c.execute("SELECT * FROM knowledge_relationships WHERE source_knowledge_id=? OR target_knowledge_id=? ORDER BY created_at DESC",(knowledge_id,knowledge_id)).fetchall()
        return [RelationshipRead(id=r["id"],source_knowledge_id=r["source_knowledge_id"],target_knowledge_id=r["target_knowledge_id"],relationship_type=r["relationship_type"],evidence=r["evidence"],confidence=r["confidence"],created_at=datetime.fromisoformat(r["created_at"])) for r in rows]
    @staticmethod
    def _to_model(r)->KnowledgeRead:
        return KnowledgeRead(id=r["id"],title=r["title"],content=r["content"],knowledge_type=r["knowledge_type"],author=r["author"],organization=r["organization"],importance=r["importance"],confidence=r["confidence"],truth_status=r["truth_status"],source=r["source"],source_memory_id=r["source_memory_id"],version=r["version"],visibility=r["visibility"],created_at=datetime.fromisoformat(r["created_at"]),updated_at=datetime.fromisoformat(r["updated_at"]))
