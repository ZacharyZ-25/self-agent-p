"""Offline integration demo. Fixed responses, no AI model or external requests."""
from app.config import Settings
from app.main import create_app
from app.models.common import TokenUsage
from app.services.provider import ProviderDelta, ProviderDone, ProviderResult


class DemoProvider:
    reply = (
        "[Offline demo / 离线演示] I am Example Candidate, a fictional character. "
        "This fixed response demonstrates the chat UI and streaming API. "
        "To generate real AI answers, configure your own model and start app.main:app."
    )

    async def complete(self, messages, user_id):
        return ProviderResult(self.reply, "offline-demo", TokenUsage(), "stop")

    async def stream(self, messages, user_id):
        for offset in range(0, len(self.reply), 12):
            yield ProviderDelta(self.reply[offset:offset + 12])
        yield ProviderDone("stop")


app = create_app(
    Settings(
        _env_file=None,
        app_env="development",
        require_approved_persona=False,
        rate_limit_per_day=100,
    ),
    provider=DemoProvider(),
)
