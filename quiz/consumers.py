from channels.generic.websocket import AsyncJsonWebsocketConsumer

class QuizConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.quiz_id = self.scope["url_route"]["kwargs"]["quiz_id"]
        self.group = f"quiz_{self.quiz_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    # Receive JSON from server-side sends and relay to clients
    async def quiz_event(self, event):
        # event = {"type": "quiz.event", "payload": {...}}
        await self.send_json(event["payload"])
