from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List

app = FastAPI()

# MÜHENDİSLİK NOTU 1: CORS Tarayıcı Güvenliği
# Tarayıcılar güvenlik gereği "file://index.html" adresinden gelen bir kodun
# "http://127.0.0.1:8000" sunucusuna bağlanmasını engeller. 
# Aşağıdaki kod tarayıcıya: "Kim gelirse gelsin kapıyı aç, ben kefilim" der.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        # Veri Yapısı: Sözlük (Dictionary)
        # Örn: { "1045": [ws_Ali, ws_Ayse], "9921": [ws_Mehmet] }
        self.active_rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept() # El sıkışma (Handshake) gerçekleşti
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = []
        self.active_rooms[room_id].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_rooms:
            if websocket in self.active_rooms[room_id]:
                self.active_rooms[room_id].remove(websocket)
            if len(self.active_rooms[room_id]) == 0:
                del self.active_rooms[room_id] # Boş odaları RAM'den sil

    async def broadcast_to_room(self, message: str, room_id: str):
        if room_id in self.active_rooms:
            for connection in self.active_rooms[room_id]:
                await connection.send_text(message)

manager = ConnectionManager()

# MÜHENDİSLİK NOTU 2: Asenkron Programlama (async / await)
# Video izlenirken sunucu saniyede yüzlerce veri alacak. 
# "async" kullanmazsak, Ali videoyu durdurduğunda sunucu Ali'nin işlemini bitirene kadar
# Ayşe'nin chat mesajını bekletir. Async sayesinde sunucu aynı anda 100 işi paralel yapar.
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Odadan biri bir şey yolladı -> Odadaki tüm bağlantılara fırlat!
            await manager.broadcast_to_room(data, room_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)