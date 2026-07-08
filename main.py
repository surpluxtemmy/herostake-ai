from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import uvicorn
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import pytz
import secrets
from fastapi import UploadFile, File

app = FastAPI(title="HeroStake AI")

NIGERIA_TZ = pytz.timezone("Africa/Lagos")

# ================== DATABASE SETUP (PostgreSQL) ==================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./platform.db"  # Local fallback

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print("✅ Database engine created")

# ================== TP/SL CHECK FUNCTION ==================
def check_take_profit_stop_loss(username: str):
    db = SessionLocal()
    try:
        user = db.execute(text("""
            SELECT balance, take_profit, stop_loss, current_profit, joined_session 
            FROM users WHERE username=:username
        """), {"username": username}).fetchone()
        
        if not user:
            return False
        
        balance, tp, sl, curr_profit, joined = user
        if not joined:
            return False
        
        tp = tp or 0
        sl = sl or 0
        balance = balance or 0.0
        curr_profit = curr_profit or 0.0

        if tp > 0 and curr_profit >= tp:
            db.execute(text("UPDATE users SET joined_session=0 WHERE username=:username"), {"username": username})
            db.commit()
            print(f"✅ TAKE PROFIT REACHED for {username}")
            return True
        
        if sl > 0:
            stop_loss_threshold = balance - sl
            if balance <= stop_loss_threshold:
                db.execute(text("UPDATE users SET joined_session=0 WHERE username=:username"), {"username": username})
                db.commit()
                print(f"⛔ STOP LOSS REACHED for {username}")
                return True
        return False
    finally:
        db.close()

# ================== SECURITY HELPERS ==================
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def sanitize_filename(filename: str) -> str:
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ["jpg", "jpeg", "png", "pdf"]:
        raise ValueError("Invalid file type")
    return f"{secrets.token_hex(16)}.{ext}"

def get_user_balance(username: str) -> float:
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT balance FROM users WHERE username=:username"), 
                          {"username": username}).fetchone()
        return float(result[0]) if result else 0.0
    finally:
        db.close()

# Global last round result
last_round_result = {
    "result": "Waiting for round...", 
    "multiplier": "0.00x", 
    "color": "text-yellow-300"
}

# ================= REAL-TIME API =================
@app.get("/api/user-status")
async def user_status(username: str):
    db = SessionLocal()
    try:
        user = db.execute(text("""
            SELECT balance, current_profit, joined_session 
            FROM users WHERE username=:username
        """), {"username": username}).fetchone()
        
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=404)
        
        balance, current_profit, joined = user
        current_profit = current_profit or 0.0

        history = db.execute(text("""SELECT result, bet_amount, profit_loss, timestamp 
                      FROM bet_history WHERE username=:username ORDER BY id DESC LIMIT 10"""), 
                      {"username": username}).fetchall()

        return {
            "balance": round(float(balance), 2),
            "current_profit": round(float(current_profit), 2),
            "joined_session": bool(joined),
            "history": [
                {
                    "result": h[0],
                    "bet": h[1],
                    "profit_loss": h[2],
                    "timestamp": h[3]
                } for h in history
            ]
        }
    finally:
        db.close()

@app.get("/api/last-result")
async def last_result():
    global last_round_result
    return last_round_result

# ================= LOGIN & REGISTER =================
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - HeroStake AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        <div class="bg-gray-900 p-10 rounded-3xl w-full max-w-md">
            <h1 class="text-5xl font-bold text-green-400 text-center mb-8">HeroStake AI</h1>
            <form action="/login" method="post" class="space-y-6">
                <input type="text" name="username" placeholder="Username" class="w-full p-5 bg-gray-800 rounded-2xl text-lg" required>
                <input type="password" name="password" placeholder="Password" class="w-full p-5 bg-gray-800 rounded-2xl text-lg" required>
                <button type="submit" class="w-full bg-green-600 hover:bg-green-700 py-6 rounded-2xl text-xl font-bold">LOGIN</button>
            </form>
            <p class="text-center mt-6 text-gray-400">Don't have an account? <a href="/register" class="text-green-400">Register</a></p>
        </div>
    </body>
    </html>
    """

# (The rest of your endpoints like /register, /dashboard, etc. can stay mostly the same. 
# But for now, redeploy this version first to test connection.)

if __name__ == "__main__":
    print("🚀 HeroStake AI Running → http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
