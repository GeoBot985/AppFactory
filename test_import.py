import sys
sys.path.append("Demo5")
from app.services.rag_service import get_rag_context
print(get_rag_context("test"))
