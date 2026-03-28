"""
RentEase - Main FastAPI entry point
Imports app from server.py for uvicorn main:app usage
"""

from server import app

@app.get("/")
async def root():
    return {"message": "RentEase API Backend - Welcome!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
