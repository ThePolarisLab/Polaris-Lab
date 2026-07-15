from app.core.database import initialize_database
from app.models.schemas import KnowledgeCreate,KnowledgeType,TruthStatus,Visibility,RelationshipCreate
from app.repositories.knowledge_repository import KnowledgeRepository

def main()->None:
    initialize_database(); repo=KnowledgeRepository()
    a=repo.create(KnowledgeCreate(title="Every Builder matters",content="Recognition is not the measure of a Builder. Contribution is.",knowledge_type=KnowledgeType.FOUNDATION_PRINCIPLE,author="Surinder Pahil",importance=5,confidence=1.0,truth_status=TruthStatus.VERIFIED,source="Polaris Foundation",visibility=Visibility.ORGANIZATION))
    b=repo.create(KnowledgeCreate(title="Foundation dedication",content="Dedicated to every Builder whose wisdom deserved to outlive them.",knowledge_type=KnowledgeType.FOUNDATION_PRINCIPLE,author="Surinder Pahil",importance=5,confidence=1.0,truth_status=TruthStatus.VERIFIED,source="Polaris Foundation",visibility=Visibility.ORGANIZATION))
    repo.create_relationship(RelationshipCreate(source_knowledge_id=a.id,target_knowledge_id=b.id,relationship_type="reinforces",evidence="Both define Polaris as a Builder-centered institution.",confidence=1.0))
    print(f"Created knowledge objects {a.id} and {b.id} with one relationship.")
if __name__=="__main__":main()
