from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from config import config
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def verify_admin(request: Request):
    if request.headers.get("X-Admin-Token") != config.ADMIN_SECRET:
        raise HTTPException(status_code=403)
    return True

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, auth=Depends(verify_admin)):
    logs = []
    log_file = "logs/api.log"
    
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            logs = f.readlines()[-100:]  # Get last 100 lines
            
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "logs": reversed(logs)}
    )
