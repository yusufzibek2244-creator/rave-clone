from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Dict, List, Any
import json

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
        if room_id in self.rooms:
            for connection in self.rooms[room_id]["connections"]:
                await connection.send_text(message)

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

# --- VİTRİN (LOBİ) İÇİN YEPYENİ BİR API ROTASI ---
@app.get("/api/rooms")
async def api_get_rooms():
    return {"active_rooms": manager.get_public_rooms()}

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