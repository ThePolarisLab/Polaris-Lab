from datetime import datetime
from app.core.database import get_connection
from app.models.schemas import MemoryCreate, MemoryRead
class MemoryRepository:
    def create(self,item:MemoryCreate)->MemoryRead:
        created_at=datetime.utcnow()
        with get_connection() as c:
            cur=c.execute("INSERT INTO memories(title,content,memory_type,source,importance,occurred_at,created_at) VALUES(?,?,?,?,?,?,?)",(item.title,item.content,item.memory_type.value,item.source,item.importance,item.occurred_at.isoformat(),created_at.isoformat()))
            mid=int(cur.lastrowid)
        return self.get(mid)
    def get(self,memory_id:int)->MemoryRead:
        with get_connection() as c: row=c.execute("SELECT * FROM memories WHERE id=?",(memory_id,)).fetchone()
        if row is None: raise KeyError(memory_id)
        return self._to_model(row)
    def list(self,query:str|None=None,limit:int=100)->list[MemoryRead]:
        sql="SELECT * FROM memories"; params=[]
        if query: sql+=" WHERE title LIKE ? OR content LIKE ?"; term=f"%{query}%"; params=[term,term]
        sql+=" ORDER BY occurred_at DESC LIMIT ?"; params.append(limit)
        with get_connection() as c: rows=c.execute(sql,params).fetchall()
        return [self._to_model(r) for r in rows]
    def count(self)->int:
        with get_connection() as c: return int(c.execute("SELECT COUNT(*) count FROM memories").fetchone()["count"])
    @staticmethod
    def _to_model(r)->MemoryRead:
        return MemoryRead(id=r["id"],title=r["title"],content=r["content"],memory_type=r["memory_type"],source=r["source"],importance=r["importance"],occurred_at=datetime.fromisoformat(r["occurred_at"]),created_at=datetime.fromisoformat(r["created_at"]))
