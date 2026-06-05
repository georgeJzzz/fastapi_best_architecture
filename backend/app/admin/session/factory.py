from backend.app.admin.session.manager import UserSessionManager
from backend.app.admin.session.store import RedisSessionStore
from backend.app.admin.session.users import SqlAlchemyUserSnapshotAdapter

user_session_manager = UserSessionManager(RedisSessionStore(), SqlAlchemyUserSnapshotAdapter())
