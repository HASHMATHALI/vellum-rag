# Import every model so string-based relationships ("ChatSession", "Document", ...) always resolve,
# regardless of which model module is imported first.
from app.models.user import AuthSession, User  # noqa: F401
from app.models.document import Document, DocumentChunk  # noqa: F401
from app.models.chat import ChatMessage, ChatSession  # noqa: F401
