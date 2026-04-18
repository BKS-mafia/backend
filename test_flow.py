import asyncio
import httpx
import websockets
import json
import uuid

API_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"

async def test_flow():
    async with httpx.AsyncClient() as client:
        # 1. Create a room
        print("Creating room...")
        room_id_str = str(uuid.uuid4())
        host_token = str(uuid.uuid4())
        response = await client.post(f"{API_URL}/api/rooms/", json={
            "room_id": room_id_str,
            "host_token": host_token,
            "status": "waiting",
            "max_players": 6,
            "min_players": 3,
            "ai_players": 2,
            "settings": {}
        })
        if response.status_code != 201:
            print(f"Failed to create room: {response.text}")
            return
        room_data = response.json()
        room_id = room_data["room_id"]
        print(f"Room created: {room_id}")

        # 2. Join room (Player 1)
        print("Joining room as Player 1...")
        player_id_str = str(uuid.uuid4())
        response = await client.post(f"{API_URL}/api/rooms/{room_id}/join", json={
            "player_id": player_id_str,
            "room_id": room_data["id"], # Use internal ID for schema validation
            "nickname": "Player 1",
            "is_ai": False
        })
        if response.status_code != 200:
            print(f"Failed to join room: {response.text}")
            return
        player1_data = response.json()
        player1_id = player1_data["id"]
        session_token = player1_data["session_token"]
        print(f"Player 1 joined: {player1_id}, token: {session_token}")

        # 3. Connect via WebSocket
        print("Connecting via WebSocket...")
        ws_url = f"{WS_URL}/ws/rooms/{room_id}?token={session_token}"
        try:
            async with websockets.connect(ws_url) as websocket:
                print("WebSocket connected!")
                
                # 4. Start game
                print("Starting game...")
                await websocket.send(json.dumps({
                    "type": "start_game",
                    "data": {}
                }))

                # Wait for game start event
                for _ in range(3):
                    msg = await websocket.recv()
                    print(f"Received: {msg}")
                    data = json.loads(msg)
                    if data.get("type") == "game_started":
                        print("Game started successfully!")
                        break
        except Exception as e:
            print(f"WebSocket error: {e}")

if __name__ == "__main__":
    asyncio.run(test_flow())
