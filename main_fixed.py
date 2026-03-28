"""
RentEase - Main FastAPI entry point
"""

import uvicorn
from server import app

@app.get("/")
async def root():
    return {"message": "RentEase API Backend - Welcome!"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
