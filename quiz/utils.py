from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def broadcast_quiz(quiz_id: int, payload: dict) -> None:
    """
    Best-effort broadcast. With InMemoryChannelLayer this works in a single
    process; if a layer isn't available, quietly no-ops so admin won't crash.
    """
    try:
        layer = get_channel_layer()
        if not layer:
            return
        async_to_sync(layer.group_send)(
            f"quiz_{quiz_id}",
            {"type": "quiz.event", "payload": payload},
        )
    except Exception:
        # Optional: add logging here
        pass
