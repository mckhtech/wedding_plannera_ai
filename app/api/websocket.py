from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from typing import Dict
import json
import asyncio
from app.database import get_db
from app.models.generation import Generation, GenerationStatus

router = APIRouter()

# Store active WebSocket connections
active_connections: Dict[int, WebSocket] = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}
    
    async def connect(self, generation_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[generation_id] = websocket
    
    def disconnect(self, generation_id: int):
        if generation_id in self.active_connections:
            del self.active_connections[generation_id]
    
    async def send_update(self, generation_id: int, message: dict):
        if generation_id in self.active_connections:
            try:
                await self.active_connections[generation_id].send_json(message)
            except:
                self.disconnect(generation_id)
    
    async def broadcast(self, message: dict):
        for connection in list(self.active_connections.values()):
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@router.websocket("/ws/generation/{generation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    generation_id: int,
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time generation updates"""
    await manager.connect(generation_id, websocket)
    
    try:
        # Send initial status
        generation = db.query(Generation).filter(Generation.id == generation_id).first()
        if generation:
            await websocket.send_json({
                "type": "status",
                "generation_id": generation_id,
                "status": generation.status.value,
                "message": "Connected to generation updates"
            })
        
        # Keep connection alive and listen for updates
        while True:
            # Check for updates every 2 seconds
            await asyncio.sleep(2)
            
            generation = db.query(Generation).filter(Generation.id == generation_id).first()
            if not generation:
                await websocket.send_json({
                    "type": "error",
                    "message": "Generation not found"
                })
                break
            
            # Send status update
            update_data = {
                "type": "status_update",
                "generation_id": generation_id,
                "status": generation.status.value,
            }
            
            if generation.status == GenerationStatus.COMPLETED:
                update_data["generated_image_url"] = f"/generated/{generation.generated_image_path.split('/')[-1]}"
                update_data["message"] = "Image generation completed!"
                await websocket.send_json(update_data)
                break
            
            elif generation.status == GenerationStatus.FAILED:
                update_data["error"] = generation.error_message
                update_data["message"] = "Image generation failed"
                await websocket.send_json(update_data)
                break
            
            elif generation.status == GenerationStatus.PROCESSING:
                update_data["message"] = "Processing your image..."
                await websocket.send_json(update_data)
            
            else:  # PENDING
                update_data["message"] = "Your request is in queue..."
                await websocket.send_json(update_data)
    
    except WebSocketDisconnect:
        manager.disconnect(generation_id)
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
        manager.disconnect(generation_id)

# Helper function to send updates from background tasks
async def notify_generation_update(generation_id: int, status: str, data: dict = None):
    """Call this from background tasks to notify connected clients"""
    message = {
        "type": "status_update",
        "generation_id": generation_id,
        "status": status,
        **(data or {})
    }
    await manager.send_update(generation_id, message)