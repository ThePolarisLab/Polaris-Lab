from datetime import datetime
from app.core.database import get_connection
from app.models.schemas import DecisionCreate, DecisionRead
class DecisionRepository:
    def create(self,item:DecisionCreate)->DecisionRead:
        created_at=datetime.utcnow()
        with get_connection() as c:
            cur=c.execute("INSERT INTO decisions(title,decision,rationale,status,decided_at,created_at) VALUES(?,?,?,?,?,?)",(item.title,item.decision,item.rationale,item.status.value,item.decided_at.isoformat(),created_at.isoformat()))
            did=int(cur.lastrowid)
        return self.get(did)
    def get(self,decision_id:int)->DecisionRead:
        with get_connection() as c: row=c.execute("SELECT * FROM decisions WHERE id=?",(decision_id,)).fetchone()
        if row is None: raise KeyError(decision_id)
        return self._to_model(row)
    def list(self,limit:int=100)->list[DecisionRead]:
        with get_connection() as c: rows=c.execute("SELECT * FROM decisions ORDER BY decided_at DESC LIMIT ?",(limit,)).fetchall()
        return [self._to_model(r) for r in rows]
    def count(self)->int:
        with get_connection() as c: return int(c.execute("SELECT COUNT(*) count FROM decisions").fetchone()["count"])
    @staticmethod
    def _to_model(r)->DecisionRead:
        return DecisionRead(id=r["id"],title=r["title"],decision=r["decision"],rationale=r["rationale"],status=r["status"],decided_at=datetime.fromisoformat(r["decided_at"]),created_at=datetime.fromisoformat(r["created_at"]))
