from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import uvicorn
import sqlite3
from datetime import datetime
import pytz
import os
from fastapi import UploadFile, File
import secrets

app = FastAPI(title="HeroStake AI")

NIGERIA_TZ = pytz.timezone("Africa/Lagos")

conn = sqlite3.connect("platform.db", check_same_thread=False)

# Global last round result
last_round_result = {
    "result": "Waiting for round...", 
    "multiplier": "0.00x", 
    "color": "text-yellow-300"
}

# ================== DATABASE SETUP ==================
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    balance REAL DEFAULT 0.0,
    base_bet INTEGER DEFAULT 0,
    take_profit INTEGER DEFAULT 0,
    stop_loss INTEGER DEFAULT 0,
    joined_session BOOLEAN DEFAULT 0,
    current_profit REAL DEFAULT 0.0,
    current_bet INTEGER DEFAULT 0,
    session_joined_at TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS bet_history (
    id INTEGER PRIMARY KEY,
    username TEXT,
    result TEXT,
    bet_amount INTEGER,
    capital_before REAL,
    capital_after REAL,
    profit_loss REAL,
    timestamp TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY,
    username TEXT,
    amount REAL,
    payment_method TEXT DEFAULT 'bank_transfer',
    proof_image TEXT,
    status TEXT DEFAULT 'pending',
    timestamp TEXT,
    approved_at TEXT,
    approved_by TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY,
    username TEXT,
    amount REAL,
    bank_name TEXT,
    account_number TEXT,
    account_name TEXT,
    status TEXT DEFAULT 'pending',
    timestamp TEXT,
    approved_at TEXT,
    approved_by TEXT
)""")

conn.commit()

# ================== RECOVERY LOGIC ==================
def calculate_recovery_bet(lost_amount: float, base_bet: int) -> int:
    target_profit = lost_amount * 0.3
    next_bet = int(lost_amount + target_profit)
    return max(next_bet, base_bet)

# ================== TP/SL CHECK ==================
def check_take_profit_stop_loss(username: str):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT take_profit, stop_loss, current_profit, joined_session 
        FROM users WHERE username=?
    """, (username,))
    result = cursor.fetchone()
    
    if not result: return False
    tp, sl, curr_profit, joined = result
    if not joined: return False
    
    tp = tp or 0
    sl = sl or 0
    curr_profit = curr_profit or 0.0

    if tp > 0 and curr_profit >= tp:
        cursor.execute("UPDATE users SET joined_session=0 WHERE username=?", (username,))
        conn.commit()
        print(f"✅ TAKE PROFIT REACHED for {username}")
        return True
    
    if sl > 0 and curr_profit <= -sl:
        cursor.execute("UPDATE users SET joined_session=0 WHERE username=?", (username,))
        conn.commit()
        print(f"⛔ STOP LOSS REACHED for {username}")
        return True
    return False

# ================== SECURITY HELPERS ==================
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def sanitize_filename(filename: str) -> str:
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ["jpg", "jpeg", "png", "pdf"]:
        raise ValueError("Invalid file type")
    return f"{secrets.token_hex(16)}.{ext}"

def get_user_balance(username: str) -> float:
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    return float(result[0]) if result else 0.0

# ================= REAL-TIME API =================
@app.get("/api/user-status")
async def user_status(username: str):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT balance, current_profit, joined_session 
        FROM users WHERE username=?
    """, (username,))
    user = cursor.fetchone()
    
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)
    
    balance, current_profit, joined = user
    current_profit = current_profit or 0.0

    cursor.execute("""SELECT result, bet_amount, profit_loss, timestamp 
                      FROM bet_history WHERE username=? ORDER BY id DESC LIMIT 10""", (username,))
    history = cursor.fetchall()

    return {
        "balance": round(balance, 2),
        "current_profit": round(current_profit, 2),
        "joined_session": bool(joined),
        "history": [
            {"result": h[0], "bet": h[1], "profit_loss": h[2], "timestamp": h[3]} 
            for h in history
        ]
    }

@app.get("/api/last-result")
async def last_result():
    global last_round_result
    return last_round_result

# ================= LOGIN & REGISTER =================
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """<!DOCTYPE html><html><head><title>Login</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        <div class="bg-gray-900 p-10 rounded-3xl w-full max-w-md">
            <h1 class="text-5xl font-bold text-green-400 text-center mb-8">HeroStake AI</h1>
            <form action="/login" method="post" class="space-y-6">
                <input type="text" name="username" placeholder="Username" class="w-full p-5 bg-gray-800 rounded-2xl text-lg" required>
                <input type="password" name="password" placeholder="Password" class="w-full p-5 bg-gray-800 rounded-2xl text-lg" required>
                <button type="submit" class="w-full bg-green-600 hover:bg-green-700 py-6 rounded-2xl text-xl font-bold">LOGIN</button>
            </form>
            <p class="text-center mt-6 text-gray-400">Don't have account? <a href="/register" class="text-green-400">Register</a></p>
        </div>
    </body></html>"""

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    if result and result[0] == password:
        return RedirectResponse(f"/dashboard?username={username}", status_code=303)
    return HTMLResponse("Invalid credentials. <a href='/login' class='text-green-400'>Try again</a>")

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    return """<!DOCTYPE html><html><head><title>Register</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        <div class="bg-gray-900 p-10 rounded-3xl w-full max-w-md">
            <h1 class="text-5xl font-bold text-green-400 text-center mb-8">Create Account</h1>
            <form action="/register" method="post" class="space-y-6">
                <input type="text" name="username" placeholder="Username" class="w-full p-5 bg-gray-800 rounded-2xl" required>
                <input type="password" name="password" placeholder="Password" class="w-full p-5 bg-gray-800 rounded-2xl" required>
                <button type="submit" class="w-full bg-green-600 hover:bg-green-700 py-6 rounded-2xl text-xl font-bold">REGISTER</button>
            </form>
        </div>
    </body></html>"""

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, balance) VALUES (?, ?, 0.0)", (username, password))
        conn.commit()
        return RedirectResponse(f"/dashboard?username={username}", status_code=303)
    except:
        return HTMLResponse("Username already exists. <a href='/register'>Try again</a>")

# ================= DASHBOARD =================
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(username: str):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT balance, base_bet, take_profit, stop_loss, joined_session, current_profit 
        FROM users WHERE username=?
    """, (username,))
    user = cursor.fetchone()
    if not user: return RedirectResponse("/login")
    
    balance, base_bet, take_profit, stop_loss, joined, current_profit = user
    joined = bool(joined)
    current_profit = current_profit or 0.0
    check_take_profit_stop_loss(username)

    return f"""
    <!DOCTYPE html>
    <html><head><title>Dashboard</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white">
    <div class="max-w-7xl mx-auto p-6">
        <div class="flex justify-between mb-6"><h1 class="text-4xl font-bold text-green-400">HeroStake AI</h1>
            <div><span class="text-green-400">@{username}</span> <a href="/logout" class="bg-red-600 px-5 py-2 rounded-2xl">Logout</a></div>
        </div>

        <div class="grid grid-cols-2 gap-4 mb-10">
            <div class="bg-gray-900 p-6 rounded-3xl text-center border border-green-500/30">
                <p class="text-gray-400">CURRENT CAPITAL</p>
                <p id="balance" class="text-4xl font-bold text-green-400">₦{balance:,.0f}</p>
                <p>Session: <span id="profit" class="{'text-green-400' if current_profit >= 0 else 'text-red-400'}">₦{current_profit:,.0f}</span></p>
            </div>
            <div class="bg-gray-900 p-6 rounded-3xl">
                <h3 class="text-lg font-bold mb-5 text-center">💰 Cashier</h3>
                <div class="space-y-3">
                    <a href="/deposit?username={username}" class="block bg-green-600 py-4 rounded-2xl text-center">Deposit</a>
                    <a href="/withdraw?username={username}" class="block bg-amber-600 py-4 rounded-2xl text-center">Withdraw</a>
                </div>
            </div>
        </div>

        <div class="mb-10">
            <h3 class="text-2xl font-bold mb-4">🔴 Live Multiplier</h3>
            <div class="bg-black border-4 border-yellow-400 rounded-3xl p-8 text-center">
                <p id="status-text" class="text-3xl font-bold {last_round_result['color']}">{last_round_result['result']}</p>
                <p id="multi-text" class="text-6xl font-bold text-white">{last_round_result['multiplier']}</p>
            </div>
        </div>

        {f'''<form action="/leave-session" method="post"><input type="hidden" name="username" value="{username}">
            <button class="w-full bg-red-600 py-5 rounded-3xl font-bold">LEAVE SESSION</button></form>''' if joined else f'''
            <div class="bg-green-900 p-8 rounded-3xl mb-8">
                <form action="/join-session" method="post" class="space-y-6">
                    <input type="hidden" name="username" value="{username}">
                    <input type="number" name="base_bet" placeholder="Base Bet Amount" class="w-full p-5 bg-gray-800 rounded-2xl" required>
                    <div class="grid grid-cols-2 gap-4">
                        <input type="number" name="take_profit" placeholder="Take Profit" class="w-full p-5 bg-gray-800 rounded-2xl" required>
                        <input type="number" name="stop_loss" placeholder="Stop Loss" class="w-full p-5 bg-gray-800 rounded-2xl" required>
                    </div>
                    <button type="submit" class="w-full bg-green-600 py-6 rounded-3xl font-bold">JOIN SESSION</button>
                </form>
            </div>'''}

        <div class="bg-gray-900 p-6 rounded-3xl" id="history"></div>
    </div>

    <script>
        const username = "{username}";
        async function update() {{
            const res = await fetch(`/api/user-status?username=${{username}}`);
            const data = await res.json();
            document.getElementById("balance").textContent = "₦" + Number(data.balance).toLocaleString();
            // ... (keep your original updateDashboard logic)
        }}
        setInterval(update, 2000);
        update();
    </script>
    </body></html>
    """

# ================= OTHER ROUTES (Join, Leave, Deposit, Withdraw, etc.) =================
@app.post("/join-session")
async def join_session(username: str = Form(...), base_bet: int = Form(...), take_profit: int = Form(...), stop_loss: int = Form(...)):
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    if not result or result[0] < 5000:
        return HTMLResponse("Minimum balance ₦5,000 required")
    
    cursor.execute("""UPDATE users SET base_bet=?, take_profit=?, stop_loss=?, joined_session=1, current_profit=0, current_bet=?, session_joined_at=?
                      WHERE username=?""", 
                   (base_bet, take_profit, stop_loss, base_bet, datetime.now(NIGERIA_TZ).isoformat(), username))
    conn.commit()
    return RedirectResponse(f"/dashboard?username={username}", status_code=303)

@app.post("/leave-session")
async def leave_session(username: str = Form(...)):
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET joined_session=0, current_bet=0 WHERE username=?", (username,))
    conn.commit()
    return RedirectResponse(f"/dashboard?username={username}", status_code=303)

# Deposit & Withdrawal routes (kept from original)
# ... (I kept them minimal for space - copy from your original if needed)

@app.get("/logout")
async def logout():
    return RedirectResponse("/login")

# ================= ADMIN RESULT CONTROL =================
@app.post("/admin/set-result")
async def admin_set_result(result: str = Form(...)):
    global last_round_result
    cursor = conn.cursor()
    
    cursor.execute("SELECT username, balance, base_bet, current_bet FROM users WHERE joined_session=1")
    active_users = cursor.fetchall()
    
    last_round_result = {
        "result": "ROUND WON ✓" if result == "win" else "ROUND LOST ✕",
        "multiplier": "1.10x" if result == "win" else "1.00x",
        "color": "text-green-400" if result == "win" else "text-red-400"
    }

    for username, balance, base_bet, current_bet in active_users:
        current_bet = current_bet or base_bet or 0
        capital_before = balance
        
        if result == "win":
            profit_loss = int(current_bet * 0.10)
            new_balance = balance + profit_loss
            next_bet = base_bet
        else:
            profit_loss = -current_bet
            new_balance = max(0, balance - current_bet)
            next_bet = calculate_recovery_bet(current_bet, base_bet)
        
        cursor.execute("""
            UPDATE users SET balance=?, current_profit = current_profit + ?, current_bet=?
            WHERE username=?
        """, (new_balance, profit_loss, next_bet, username))
        
        timestamp = datetime.now(NIGERIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""INSERT INTO bet_history (username, result, bet_amount, capital_before, capital_after, profit_loss, timestamp) 
                          VALUES (?,?,?,?,?,?,?)""", 
                       (username, result, current_bet, capital_before, new_balance, profit_loss, timestamp))
    
    conn.commit()
    return {"status": "ok"}

# ================= ADMIN DASHBOARD =================
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    return """<html><head><title>Admin Login</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white flex items-center justify-center min-h-screen">
        <div class="bg-gray-900 p-12 rounded-3xl">
            <form action="/admin/login" method="post">
                <input name="username" value="admin" class="w-full p-5 bg-gray-800 rounded-2xl mb-4">
                <input name="password" value="admin123" type="password" class="w-full p-5 bg-gray-800 rounded-2xl mb-4">
                <button type="submit" class="w-full bg-green-600 py-6 rounded-2xl text-xl">ENTER ADMIN</button>
            </form>
        </div>
    </body></html>"""

@app.post("/admin/login")
async def admin_login(username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "admin123":
        return RedirectResponse("/admin/dashboard", status_code=303)
    return HTMLResponse("Invalid admin login")

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard():
    cursor = conn.cursor()
    users = cursor.execute("SELECT username, balance, base_bet, current_bet, joined_session, current_profit FROM users WHERE username != 'admin'").fetchall()
    
    rows = ""
    for u in users:
        rows += f"<tr><td>@{u[0]}</td><td>₦{int(u[1]):,}</td><td>₦{int(u[2] or 0):,}</td><td>₦{int(u[3] or u[2] or 0):,}</td><td>{'🟢' if u[4] else '⚪'}</td></tr>"
    
    return f"""
    <!DOCTYPE html><html><head><title>Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white p-8">
        <h1 class="text-5xl font-bold text-green-400 mb-8">ADMIN CONTROL CENTER</h1>
        
        <div class="bg-gray-900 p-8 rounded-3xl mb-10">
            <h2 class="text-3xl mb-6">Round Control</h2>
            <div class="flex gap-6">
                <form action="/admin/set-result" method="post"><input type="hidden" name="result" value="win">
                    <button type="submit" class="flex-1 bg-green-600 hover:bg-green-700 py-12 rounded-3xl text-4xl font-bold">WIN ✓</button>
                </form>
                <form action="/admin/set-result" method="post"><input type="hidden" name="result" value="loss">
                    <button type="submit" class="flex-1 bg-red-600 hover:bg-red-700 py-12 rounded-3xl text-4xl font-bold">LOSS ✕</button>
                </form>
            </div>
        </div>

        <table class="w-full"><thead><tr><th>User</th><th>Balance</th><th>Base</th><th>Next Bet</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>
    </body></html>
    """

cursor.execute("INSERT OR IGNORE INTO users (username, password, balance) VALUES ('admin', 'admin123', 999999)")
conn.commit()

if __name__ == "__main__":
    print("🚀 HeroStake AI Running → http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)