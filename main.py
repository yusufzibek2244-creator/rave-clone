from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Dict, Any
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        # ESKİSİ GİBİ DEĞİL: Artık odaları sadece liste olarak değil, detaylı bir sözlük (kimlik) olarak tutuyoruz.
        self.rooms: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        
        # Eğer oda ilk defa kuruluyorsa, odanın kimlik kartını oluştur
        if room_id not in self.rooms:
            self.rooms[room_id] = {
                "connections": [],
                "is_public": True,     # Varsayılan olarak odalar herkese açık (Public)
                "video_id": "Bekleniyor",
                "host": "Bilinmiyor"
            }
            
        self.rooms[room_id]["connections"].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.rooms:
            if websocket in self.rooms[room_id]["connections"]:
                self.rooms[room_id]["connections"].remove(websocket)
            # Odada kimse kalmadıysa odayı sil
            if len(self.rooms[room_id]["connections"]) == 0:
                del self.rooms[room_id]

    async def broadcast_to_room(self, message: str, room_id: str):
        if room_id not in self.rooms:
            return
        dead = []
        for connection in self.rooms[room_id]["connections"]:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection, room_id)

    # LOBİ VİTRİNİ İÇİN YENİ MOTOR: Sadece Public olan odaları paketleyip listeler
    def get_public_rooms(self):
        public_rooms = []
        for r_id, r_data in self.rooms.items():
            if r_data["is_public"]:
                public_rooms.append({
                    "room_id": r_id,
                    "users_count": len(r_data["connections"]),
                    "video_id": r_data["video_id"],
                    "host": r_data["host"]
                })
        return public_rooms

manager = ConnectionManager()

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_text()
            
            # Gelen mesajı JSON olarak okuyup, odanın kimlik kartını güncelliyoruz (Örn: Video değişirse veya Oda kilitlenirse)
            try:
                parsed_data = json.loads(data)
                if parsed_data.get("type") == "room_update":
                    if "video_id" in parsed_data:
                        manager.rooms[room_id]["video_id"] = parsed_data["video_id"]
                    if "is_public" in parsed_data:
                        manager.rooms[room_id]["is_public"] = parsed_data["is_public"]
                    if "host" in parsed_data:
                        manager.rooms[room_id]["host"] = parsed_data["host"]
            except:
                pass # JSON değilse normal mesajdır, geç

            await manager.broadcast_to_room(data, room_id)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- VİTRİN (LOBİ) İÇİN YEPYENİ BİR API ROTASI ---
@app.get("/api/rooms")
async def api_get_rooms():
    return {"active_rooms": manager.get_public_rooms()}

@app.get("/api/room/{room_id}")
async def api_get_room(room_id: str):
    room = manager.rooms.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")
    return {
        "room_id": room_id,
        "video_id": room["video_id"],
        "is_public": room["is_public"],
        "host": room["host"],
        "users_count": len(room["connections"]),
    }

# --- STANDART DOSYA ROTALARI ---
@app.get("/")
async def serve_home():
    return FileResponse("index.html")

@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse("manifest.json")

@app.get("/sw.js")
async def serve_sw():
    return FileResponse("sw.js")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        ws_ping_interval=20,
        ws_ping_timeout=20,
    )