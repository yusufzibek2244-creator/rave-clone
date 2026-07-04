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
        self.rooms: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, username: str):
        await websocket.accept()
        
        # Oda ilk defa kuruluyorsa
        if room_id not in self.rooms:
            self.rooms[room_id] = {
                "clients": {},          # websocket -> username eşleşmesi
                "is_public": True,
                "video_id": "Bekleniyor",
                "host": username        # Odayı kuran ilk kişi yöneticidir
            }
            
        self.rooms[room_id]["clients"][websocket] = username
        await self.broadcast_user_list(room_id)
        await self.broadcast_to_room(json.dumps({"type": "chat", "sender": "Sistem", "text": f"{username} odaya katıldı.", "color": "text-emerald-400"}), room_id)

    async def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.rooms:
            room = self.rooms[room_id]
            username = room["clients"].pop(websocket, None)
            
            # Odada kimse kalmadıysa sil
            if len(room["clients"]) == 0:
                del self.rooms[room_id]
            else:
                # Çıkan kişi yöneticiyse, sıradaki kişiye yöneticiliği devret
                if room["host"] == username:
                    new_host_ws = list(room["clients"].keys())[0]
                    room["host"] = room["clients"][new_host_ws]
                    await self.broadcast_to_room(json.dumps({"type": "chat", "sender": "Sistem", "text": f"Yönetici ayrıldı. Yeni yönetici: {room['host']}", "color": "text-amber-500"}), room_id)
                
                await self.broadcast_user_list(room_id)
                await self.broadcast_to_room(json.dumps({"type": "chat", "sender": "Sistem", "text": f"{username} odadan ayrıldı.", "color": "text-gray-500"}), room_id)

    async def broadcast_to_room(self, message: str, room_id: str, exclude: WebSocket = None):
        if room_id not in self.rooms:
            return
        dead = []
        for connection in self.rooms[room_id]["clients"]:
            if connection == exclude: continue
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        
        for connection in dead:
            await self.disconnect(connection, room_id)

    async def broadcast_user_list(self, room_id: str):
        if room_id not in self.rooms:
            return
        room = self.rooms[room_id]
        users = list(room["clients"].values())
        data = json.dumps({
            "type": "user_list",
            "users": users,
            "host": room["host"]
        })
        await self.broadcast_to_room(data, room_id)

    def get_public_rooms(self):
        public_rooms = []
        for r_id, r_data in self.rooms.items():
            if r_data["is_public"]:
                public_rooms.append({
                    "room_id": r_id,
                    "users_count": len(r_data["clients"]),
                    "video_id": r_data["video_id"],
                    "host": r_data["host"]
                })
        return public_rooms

manager = ConnectionManager()

# WebSoket bağlantısına username parametresini ekledik
@app.websocket("/ws/{room_id}/{username}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, username: str):
    await manager.connect(websocket, room_id, username)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed_data = json.loads(data)
                msg_type = parsed_data.get("type")
                room = manager.rooms[room_id]

                # Sadece yönetici videoyu senkronize edebilir
                if msg_type == "sync":
                    if room["host"] == username:
                        await manager.broadcast_to_room(data, room_id, exclude=websocket)
                
                # Sadece yönetici birini odadan atabilir
                elif msg_type == "kick":
                    if room["host"] == username:
                        target = parsed_data.get("target")
                        for ws, uname in list(room["clients"].items()):
                            if uname == target:
                                await ws.send_text(json.dumps({"type": "kicked"}))
                                await ws.close()
                                break
                
                # Sadece yönetici yöneticiliği devredebilir
                elif msg_type == "transfer_host":
                    if room["host"] == username:
                        room["host"] = parsed_data.get("target")
                        await manager.broadcast_user_list(room_id)
                        await manager.broadcast_to_room(json.dumps({"type": "chat", "sender": "Sistem", "text": f"👑 {username}, yöneticiliği {room['host']} kişisine devretti.", "color": "text-rooms-accent"}), room_id)

                # Sohbet mesajları herkes için serbest
                elif msg_type == "chat":
                    await manager.broadcast_to_room(data, room_id)
                
                # Odaya yeni katılan misafirin videonun nerede olduğunu sorması
                elif msg_type == "request_sync":
                    await manager.broadcast_to_room(data, room_id, exclude=websocket)
                
                # Oda güncellemeleri
                elif msg_type == "room_update":
                    if "video_id" in parsed_data:
                        room["video_id"] = parsed_data["video_id"]
                    if "is_public" in parsed_data:
                        room["is_public"] = parsed_data["is_public"]

            except:
                pass 
            
    except WebSocketDisconnect:
        await manager.disconnect(websocket, room_id)

@app.get("/health")
async def health():
    return {"status": "ok"}

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
        "users_count": len(room["clients"]),
    }

@app.get("/")
async def serve_home(): return FileResponse("index.html")
@app.get("/manifest.json")
async def serve_manifest(): return FileResponse("manifest.json")
@app.get("/sw.js")
async def serve_sw(): return FileResponse("sw.js")