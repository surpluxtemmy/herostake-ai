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

# ================== TP/SL CHECK FUNCTION ==================
def check_take_profit_stop_loss(username: str):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT take_profit, stop_loss, current_profit, joined_session 
        FROM users WHERE username=?
    """, (username,))
    result = cursor.fetchone()
    
    if not result:
        return False
    
    tp, sl, curr_profit, joined = result
    if not joined:
        return False
    
    tp = tp or 0
    sl = sl or 0
    curr_profit = curr_profit or 0.0

    if tp > 0 and curr_profit >= tp:
        cursor.execute("UPDATE users SET joined_session=0 WHERE username=?", (username,))
        conn.commit()
        print(f"✅ TAKE PROFIT REACHED for {username} (+₦{curr_profit:,.0f}) → Session closed")
        return True
    
    if sl > 0 and curr_profit <= -sl:
        cursor.execute("UPDATE users SET joined_session=0 WHERE username=?", (username,))
        conn.commit()
        print(f"⛔ STOP LOSS REACHED for {username} (-₦{abs(curr_profit):,.0f}) → Session closed")
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
            {
                "result": h[0],
                "bet": h[1],
                "profit_loss": h[2],
                "timestamp": h[3]
            } for h in history
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
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Register</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        <div class="bg-gray-900 p-10 rounded-3xl w-full max-w-md">
            <h1 class="text-5xl font-bold text-green-400 text-center mb-8">Create Account</h1>
            <form action="/register" method="post" class="space-y-6">
                <input type="text" name="username" placeholder="Username" class="w-full p-5 bg-gray-800 rounded-2xl" required>
                <input type="password" name="password" placeholder="Password" class="w-full p-5 bg-gray-800 rounded-2xl" required>
                <button type="submit" class="w-full bg-green-600 hover:bg-green-700 py-6 rounded-2xl text-xl font-bold">REGISTER</button>
            </form>
        </div>
    </body>
    </html>
    """

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
    
    if not user:
        return RedirectResponse("/login")
    
    balance, base_bet, take_profit, stop_loss, joined, current_profit = user
    joined = bool(joined)
    current_profit = current_profit or 0.0

    check_take_profit_stop_loss(username)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - HeroStake AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body class="bg-gray-950 text-white">
    <div class="max-w-7xl mx-auto p-4 md:p-6">

        <div class="flex justify-between items-center mb-6">
            <h1 class="text-4xl font-bold text-green-400">HeroStake AI</h1>
            <div class="flex items-center gap-4">
                <span class="text-green-400">@{username}</span>
                <a href="/logout" class="bg-red-600 hover:bg-red-700 px-5 py-2 rounded-2xl text-sm">Logout</a>
            </div>
        </div>

        <div class="bg-green-900 border border-green-400 rounded-3xl p-5 text-center mb-8 text-base font-semibold">
            ✅ SESSION ACTIVE (24/7 - Always Open)
        </div>

        <!-- Capital + Cashier -->
        <div class="grid grid-cols-2 gap-4 mb-10">
            <div class="bg-gray-900 rounded-3xl p-6 text-center border border-green-500/30">
                <p class="text-gray-400 text-xs tracking-widest">CURRENT CAPITAL</p>
                <p id="balance" class="text-4xl font-bold text-green-400 mt-3">₦{balance:,.0f}</p>
                <p class="mt-4 text-sm">Session: <span id="profit" class="font-bold {'text-green-400' if current_profit >= 0 else 'text-red-400'}">₦{current_profit:,.0f}</span></p>
            </div>

            <div class="bg-gray-900 rounded-3xl p-6">
                <h3 class="text-lg font-bold mb-5 text-center">💰 Cashier</h3>
                <div class="space-y-3">
                    <a href="/deposit?username={username}" class="block w-full bg-green-600 hover:bg-green-700 py-4 rounded-2xl text-center font-semibold">Deposit</a>
                    <a href="/withdraw?username={username}" class="block w-full bg-amber-600 hover:bg-amber-700 py-4 rounded-2xl text-center font-semibold">Withdraw</a>
                    <a href="/history?username={username}" class="block w-full bg-gray-700 hover:bg-gray-600 py-3 rounded-2xl text-center text-sm">View Transaction History</a>
                </div>
            </div>
        </div>

        <!-- Live Multiplier -->
        <div class="mb-10">
            <h3 class="text-2xl font-bold mb-4">🔴 Live Multiplier</h3>
            <div class="bg-black border-4 border-yellow-400 rounded-3xl p-8 text-center">
                <div class="flex flex-col items-center gap-4 py-8">
                    <p id="status-text" class="text-3xl font-bold {last_round_result['color']}">{last_round_result['result']}</p>
                    <p id="multi-text" class="text-6xl font-bold text-white tracking-wider">{last_round_result['multiplier']}</p>
                </div>
            </div>
        </div>

        <!-- Join / Leave -->
        {f'''
        <div class="mb-8">
            <form action="/leave-session" method="post">
                <input type="hidden" name="username" value="{username}">
                <button type="submit" class="w-full bg-red-600 hover:bg-red-700 py-5 rounded-3xl font-bold">⛔ LEAVE SESSION</button>
            </form>
        </div>
        ''' if joined else f'''
        <div class="bg-green-900 border border-green-400 rounded-3xl p-8 mb-8">
            <h3 class="text-2xl font-bold mb-6 text-center">Join Trading Session</h3>
            <form action="/join-session" method="post" class="space-y-6 max-w-lg mx-auto">
                <input type="hidden" name="username" value="{username}">
                
                <div>
                    <label class="block text-gray-400 mb-2">Base Bet Amount (₦)</label>
                    <input type="number" name="base_bet" id="base_bet" 
                           class="w-full p-5 bg-gray-800 rounded-2xl text-lg"  required>
                    <p class="text-xs text-gray-500 mt-2" id="bet_info">
                        Recommended: 0.25% of your balance • Max: 0.5%
                    </p>
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-gray-400 mb-2">Take Profit (₦)</label>
                        <input type="number" name="take_profit" placeholder="Take Profit" 
                               class="w-full p-5 bg-gray-800 rounded-2xl" min="500" required>
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-2">Stop Loss (₦)</label>
                        <input type="number" name="stop_loss" placeholder="Stop Loss" 
                               class="w-full p-5 bg-gray-800 rounded-2xl" min="500" required>
                    </div>
                </div>
                
                <button type="submit" class="w-full bg-green-600 hover:bg-green-700 py-6 rounded-3xl font-bold text-xl">
                    JOIN SESSION
                </button>
            </form>
        </div>
        '''}

        <!-- Recent Activity -->
        <div class="bg-gray-900 rounded-3xl p-6">
            <h3 class="text-2xl font-bold mb-6">Recent Activity</h3>
            <div id="history" class="space-y-4"></div>
        </div>
    </div>

    <script>
        const username = "{username}";
        const currentBalance = {balance};

        async function updateDashboard() {{
            try {{
                const res = await fetch(`/api/user-status?username=${{username}}`);
                const data = await res.json();

                document.getElementById("balance").textContent = "₦" + Number(data.balance).toLocaleString();
                
                const profitEl = document.getElementById("profit");
                profitEl.textContent = "₦" + Number(data.current_profit).toLocaleString();
                profitEl.className = Number(data.current_profit) >= 0 ? "font-bold text-green-400" : "font-bold text-red-400";

                // Recent Activity
                let html = "";
                data.history.forEach(h => {{
                    const color = h.profit_loss > 0 ? "text-green-400" : "text-red-400";
                    html += `
                    <div class="flex justify-between items-center bg-gray-800 p-5 rounded-2xl">
                        <div>
                            <span class="${{h.result === 'win' ? 'text-green-400' : 'text-red-400'}} font-bold">${{h.result.toUpperCase()}}</span>
                            <span class="ml-4 text-gray-300">₦${{h.bet.toLocaleString()}}</span>
                        </div>
                        <div class="text-right">
                            <p class="text-xs text-gray-500">${{h.timestamp}}</p>
                            <p class="${{color}} font-medium">${{h.profit_loss > 0 ? '+' : ''}}₦${{Math.abs(h.profit_loss).toLocaleString()}}</p>
                        </div>
                    </div>`;
                }});
                document.getElementById("history").innerHTML = html || '<p class="text-gray-400 py-12 text-center">No activity yet</p>';
            }} catch(e) {{ console.log(e); }}
        }}

        function updateLiveMultiplier() {{
            fetch('/api/last-result')
                .then(res => res.json())
                .then(data => {{
                    document.getElementById("status-text").textContent = data.result;
                    document.getElementById("status-text").className = `text-3xl font-bold ${{data.color}}`;
                    document.getElementById("multi-text").textContent = data.multiplier;
                }})
                .catch(() => {{}});
        }}

        // Auto-fill + Limit base bet to 0.5%
        function setupBaseBet() {{
            const input = document.getElementById("base_bet");
            if (!input || currentBalance < 5000) return;

            const maxBet = Math.floor(currentBalance * 0.005);
            const recommended = Math.floor(currentBalance * 0.0025);

            input.max = maxBet;
            input.value = recommended;

            input.addEventListener("input", function() {{
                let value = parseInt(this.value) || 0;
                if (value > maxBet) this.value = maxBet;
            }});
        }}

        setInterval(updateDashboard, 2000);
        setInterval(updateLiveMultiplier, 600);

        updateDashboard();
        updateLiveMultiplier();
        setTimeout(setupBaseBet, 300);
    </script>
    </body>
    </html>
    """

# ================= OTHER ENDPOINTS =================
@app.get("/logout")
async def logout():
    return RedirectResponse("/login")

@app.post("/join-session")
async def join_session(username: str = Form(...), base_bet: int = Form(...), take_profit: int = Form(...), stop_loss: int = Form(...)):
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    
    if not result or result[0] < 5000:
        return HTMLResponse(f"""
            <h2 class="text-red-400 text-center mt-10">❌ Cannot Join Session</h2>
            <p class="text-center mt-4">You need a minimum balance of ₦5,000 to join a trading session.</p>
            <a href="/dashboard?username={username}" class="text-green-400 block text-center mt-8">← Back to Dashboard</a>
        """)
    
    max_bet = int(result[0] * 0.005)
    if base_bet > max_bet:
        base_bet = max_bet
    
    cursor.execute("""UPDATE users SET base_bet=?, take_profit=?, stop_loss=?, joined_session=1, current_profit=0, session_joined_at=? 
                      WHERE username=?""", 
                   (base_bet, take_profit, stop_loss, datetime.now(NIGERIA_TZ).isoformat(), username))
    conn.commit()
    return RedirectResponse(f"/dashboard?username={username}", status_code=303)

@app.post("/leave-session")
async def leave_session(username: str = Form(...)):
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET joined_session=0, base_bet=0 WHERE username=?", (username,))
    conn.commit()
    return RedirectResponse(f"/dashboard?username={username}", status_code=303)

# ================= DEPOSIT ROUTES =================
@app.get("/deposit", response_class=HTMLResponse)
async def deposit_page(username: str):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Deposit - HeroStake AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white min-h-screen">
        <div class="max-w-2xl mx-auto p-6">
            <a href="/dashboard?username={username}" class="text-green-400 mb-6 inline-block">← Back to Dashboard</a>
            <h1 class="text-4xl font-bold text-green-400 mb-8">Make a Deposit</h1>
            
            <div class="bg-gray-900 rounded-3xl p-8 mb-8">
                <h2 class="text-2xl font-bold mb-6">Bank Details</h2>
                <div class="bg-gray-800 p-6 rounded-2xl space-y-4 text-lg">
                    <p><strong>Bank Name:</strong> GTBank</p>
                    <p><strong>Account Name:</strong> HeroStake AI Ltd</p>
                    <p><strong>Account Number:</strong> 0123456789</p>
                    <p class="text-yellow-400 text-sm">Send exactly the amount you enter below</p>
                </div>
            </div>

            <form action="/deposit/submit" method="post" enctype="multipart/form-data" class="space-y-6">
                <input type="hidden" name="username" value="{username}">
                <div>
                    <label class="block text-gray-400 mb-2">Deposit Amount (₦)</label>
                    <input type="number" name="amount" min="1000" step="100" 
                           class="w-full p-5 bg-gray-800 rounded-2xl text-2xl" required>
                </div>
                
                <div>
                    <label class="block text-gray-400 mb-2">Upload Payment Proof</label>
                    <input type="file" name="proof" accept="image/*,.pdf" 
                           class="w-full p-4 bg-gray-800 rounded-2xl" required>
                </div>
                
                <button type="submit" 
                        class="w-full bg-green-600 hover:bg-green-700 py-6 rounded-3xl text-xl font-bold">
                    Submit Deposit
                </button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/deposit/submit")
async def deposit_submit(
    username: str = Form(...),
    amount: float = Form(...),
    proof: UploadFile = File(...)
):
    if amount < 1000:
        return HTMLResponse("Minimum deposit is ₦1,000", status_code=400)
    
    try:
        filename = sanitize_filename(proof.filename)
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        with open(file_path, "wb") as f:
            content = await proof.read()
            f.write(content)
        
        cursor = conn.cursor()
        timestamp = datetime.now(NIGERIA_TZ).isoformat()
        
        cursor.execute("""
            INSERT INTO deposits (username, amount, proof_image, status, timestamp)
            VALUES (?, ?, ?, 'pending', ?)
        """, (username, amount, file_path, timestamp))
        conn.commit()
        
        return HTMLResponse(f"""
            <h2 class="text-green-400 text-center mt-10">Deposit Request Submitted Successfully!</h2>
            <p class="text-center mt-4">Status: <strong>Pending</strong></p>
            <a href="/dashboard?username={username}" class="text-green-400 block text-center mt-8">← Back to Dashboard</a>
        """)
    except Exception as e:
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

# ================= TRANSACTION HISTORY =================
@app.get("/history", response_class=HTMLResponse)
async def transaction_history(username: str):
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 'Deposit' as type, amount, status, timestamp 
        FROM deposits WHERE username=? 
    """, (username,))
    deposits = cursor.fetchall()
    
    cursor.execute("""
        SELECT 'Withdrawal' as type, amount, status, timestamp 
        FROM withdrawals WHERE username=? 
    """, (username,))
    withdrawals = cursor.fetchall()
    
    all_transactions = []
    for d in deposits:
        all_transactions.append((*d, 'green'))
    for w in withdrawals:
        all_transactions.append((*w, 'amber'))
    
    all_transactions.sort(key=lambda x: x[3], reverse=True)
    
    rows = ""
    for tx in all_transactions:
        tx_type, amount, status, timestamp, color = tx
        status_color = "text-yellow-400" if status == "pending" else "text-green-400"
        sign = "+" if tx_type == "Deposit" else "-"
        
        rows += f"""
        <div class="flex justify-between items-center bg-gray-800 p-5 rounded-2xl">
            <div>
                <p class="font-bold { 'text-green-400' if tx_type == 'Deposit' else 'text-amber-400'}">
                    {sign} ₦{amount:,.0f}
                </p>
                <p class="text-xs text-gray-500">{timestamp}</p>
            </div>
            <div class="text-right">
                <span class="font-semibold { 'text-green-400' if tx_type == 'Deposit' else 'text-amber-400'}">{tx_type}</span><br>
                <span class="{status_color} text-sm">{status.upper()}</span>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transaction History - HeroStake AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white p-6">
        <div class="max-w-2xl mx-auto">
            <a href="/dashboard?username={username}" class="text-green-400 mb-6 inline-block">← Back to Dashboard</a>
            <h1 class="text-3xl font-bold text-green-400 mb-8">Transaction History</h1>
            <div class="space-y-4">
                {rows or '<p class="text-gray-400 text-center py-12">No transactions yet</p>'}
            </div>
        </div>
    </body>
    </html>
    """

# ================= WITHDRAWAL ROUTES =================
@app.get("/withdraw", response_class=HTMLResponse)
async def withdraw_page(username: str):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Withdraw - HeroStake AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white min-h-screen">
        <div class="max-w-2xl mx-auto p-6">
            <a href="/dashboard?username={username}" class="text-green-400 mb-6 inline-block">← Back to Dashboard</a>
            <h1 class="text-4xl font-bold text-amber-400 mb-8">Request Withdrawal</h1>
            
            <form action="/withdraw/submit" method="post" class="bg-gray-900 p-8 rounded-3xl space-y-6">
                <input type="hidden" name="username" value="{username}">
                
                <div>
                    <label class="block text-gray-400 mb-2">Amount (₦)</label>
                    <input type="number" name="amount" min="2000" step="100" 
                           class="w-full p-5 bg-gray-800 rounded-2xl text-2xl" required>
                </div>
                
                <div>
                    <label class="block text-gray-400 mb-2">Bank Name</label>
                    <input type="text" name="bank_name" required class="w-full p-5 bg-gray-800 rounded-2xl">
                </div>
                
                <div>
                    <label class="block text-gray-400 mb-2">Account Number</label>
                    <input type="text" name="account_number" required class="w-full p-5 bg-gray-800 rounded-2xl">
                </div>
                
                <div>
                    <label class="block text-gray-400 mb-2">Account Name</label>
                    <input type="text" name="account_name" required class="w-full p-5 bg-gray-800 rounded-2xl">
                </div>
                
                <button type="submit" 
                        class="w-full bg-amber-600 hover:bg-amber-700 py-6 rounded-3xl text-xl font-bold">
                    Submit Withdrawal Request
                </button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/withdraw/submit")
async def withdraw_submit(
    username: str = Form(...),
    amount: float = Form(...),
    bank_name: str = Form(...),
    account_number: str = Form(...),
    account_name: str = Form(...)
):
    balance = get_user_balance(username)
    if amount > balance:
        return HTMLResponse("Insufficient balance", status_code=400)
    if amount < 2000:
        return HTMLResponse("Minimum withdrawal is ₦2,000", status_code=400)
    
    cursor = conn.cursor()
    timestamp = datetime.now(NIGERIA_TZ).isoformat()
    
    cursor.execute("""
        INSERT INTO withdrawals (username, amount, bank_name, account_number, account_name, status, timestamp)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (username, amount, bank_name, account_number, account_name, timestamp))
    conn.commit()
    
    return HTMLResponse(f"""
        <h2 class="text-amber-400 text-center mt-10">Withdrawal Request Submitted!</h2>
        <p class="text-center mt-4">Status: <strong>Pending Approval</strong></p>
        <a href="/dashboard?username={username}" class="text-green-400 block text-center mt-8">← Back to Dashboard</a>
    """)

# ================= BET RESULT =================
@app.post("/api/bet-result")
async def bet_result(data: dict):
    username = data.get("username")
    result = data.get("result")
    user_bet = data.get("user_bet", 0)
    capital_before = data.get("capital_before", 0)
    capital_after = data.get("new_capital", 0)
    profit_loss = capital_after - capital_before if capital_after is not None else 0

    global last_round_result
    last_round_result = {
        "result": "ROUND WON ✓" if result == "win" else "ROUND LOST ✕",
        "multiplier": "1.10x" if result == "win" else "1.00x",
        "color": "text-green-400" if result == "win" else "text-red-400"
    }

    if username and capital_after is not None:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET balance = ?, 
                current_profit = current_profit + ? 
            WHERE username=?
        """, (capital_after, profit_loss, username))
        
        conn.commit()
        check_take_profit_stop_loss(username)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""INSERT INTO bet_history 
                          (username, result, bet_amount, capital_before, capital_after, profit_loss, timestamp) 
                          VALUES (?,?,?,?,?,?,?)""", 
                       (username, result, user_bet, capital_before, capital_after, profit_loss, timestamp))
        conn.commit()

    return {"status": "ok"}

# ================== ADMIN PORTAL ==================
def is_admin(username: str):
    return username.lower() == "admin"

cursor.execute("INSERT OR IGNORE INTO users (username, password, balance) VALUES ('admin', 'admin123', 999999)")
conn.commit()

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login - HeroStake AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    </head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        <div class="bg-gray-900 p-12 rounded-3xl w-full max-w-md border border-green-500/30">
            <div class="flex justify-center mb-6">
                <i class="fas fa-shield-alt text-7xl text-green-400"></i>
            </div>
            <h1 class="text-5xl font-bold text-center text-green-400 mb-2">Admin Portal</h1>
            <p class="text-center text-gray-400 mb-10">HeroStake AI Control Center</p>
            
            <form action="/admin/login" method="post" class="space-y-6">
                <input type="text" name="username" value="admin" placeholder="Username" 
                       class="w-full p-5 bg-gray-800 rounded-2xl text-lg" required>
                <input type="password" name="password" value="admin123" placeholder="Password" 
                       class="w-full p-5 bg-gray-800 rounded-2xl text-lg" required>
                <button type="submit" class="w-full bg-green-600 hover:bg-green-700 py-6 rounded-2xl text-xl font-bold">
                    ENTER CONTROL ROOM
                </button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/login")
async def admin_login(username: str = Form(...), password: str = Form(...)):
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    if result and result[0] == password and is_admin(username):
        return RedirectResponse("/admin/dashboard", status_code=303)
    return HTMLResponse("Invalid admin credentials. <a href='/admin/login' class='text-green-400'>Try again</a>")

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard():
    cursor = conn.cursor()
    
    total_users = cursor.execute("SELECT COUNT(*) FROM users WHERE username != 'admin'").fetchone()[0]
    total_balance = cursor.execute("SELECT COALESCE(SUM(balance), 0) FROM users").fetchone()[0]
    active_sessions = cursor.execute("SELECT COUNT(*) FROM users WHERE joined_session = 1").fetchone()[0]
    total_bets = cursor.execute("SELECT COUNT(*) FROM bet_history").fetchone()[0]

    users = cursor.execute("""
        SELECT username, balance, joined_session, current_profit 
        FROM users WHERE username != 'admin' 
        ORDER BY balance DESC
    """).fetchall()

    user_rows = ""
    for row in users:
        user_rows += """
        <tr class="border-b border-gray-800 hover:bg-gray-800/50">
            <td class="py-5 font-medium">@{}</td>
            <td class="py-5 text-right font-bold text-green-400">₦{:,}</td>
            <td class="py-5 text-center">{}</td>
            <td class="py-5 text-right {}">₦{:,}</td>
            <td class="py-5 text-center">
                <a href="/admin/user/{}" class="text-blue-400 hover:underline">Manage</a>
            </td>
        </tr>
        """.format(
            row[0],
            int(row[1]),
            "🟢 Active" if row[2] else "⚪ Inactive",
            "text-green-400" if (row[3] or 0) >= 0 else "text-red-400",
            int(row[3] or 0),
            row[0]
        )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard - HeroStake AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    </head>
    <body class="bg-gray-950 text-white">
    <div class="max-w-7xl mx-auto p-8">
        <div class="flex justify-between items-center mb-12">
            <h1 class="text-5xl font-bold text-green-400 flex items-center gap-4">
                <i class="fas fa-shield-alt"></i> ADMIN CONTROL CENTER
            </h1>
            <a href="/admin/logout" class="bg-red-600 hover:bg-red-700 px-8 py-4 rounded-2xl font-semibold">Logout</a>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-6 mb-12">
            <div class="bg-gray-900 rounded-3xl p-8 text-center border border-green-500/20">
                <p class="text-gray-400">Total Users</p>
                <p class="text-5xl font-bold mt-3">{total_users}</p>
            </div>
            <div class="bg-gray-900 rounded-3xl p-8 text-center border border-green-500/20">
                <p class="text-gray-400">Total Capital</p>
                <p class="text-5xl font-bold text-green-400 mt-3">₦{total_balance:,.0f}</p>
            </div>
            <div class="bg-gray-900 rounded-3xl p-8 text-center border border-green-500/20">
                <p class="text-gray-400">Active Sessions</p>
                <p class="text-5xl font-bold text-yellow-400 mt-3">{active_sessions}</p>
            </div>
            <div class="bg-gray-900 rounded-3xl p-8 text-center border border-green-500/20">
                <p class="text-gray-400">Total Bets</p>
                <p class="text-5xl font-bold mt-3">{total_bets}</p>
            </div>
        </div>

        <div class="bg-gray-900 rounded-3xl p-8">
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-3xl font-bold">User Management</h2>
                <input type="text" id="search" placeholder="Search users..." 
                       class="bg-gray-800 px-6 py-3 rounded-2xl w-96 focus:outline-none">
            </div>
            
            <table class="w-full">
                <thead>
                    <tr class="border-b border-gray-700 text-left">
                        <th class="pb-5">Username</th>
                        <th class="pb-5 text-right">Balance</th>
                        <th class="pb-5 text-center">Session</th>
                        <th class="pb-5 text-right">Current P/L</th>
                        <th class="pb-5 text-center">Action</th>
                    </tr>
                </thead>
                <tbody id="userTable">
                    {user_rows}
                </tbody>
            </table>
        </div>
        
        <div class="mt-8 text-center">
            <a href="/admin/transactions" class="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-2xl text-lg font-semibold">
                Manage Deposits & Withdrawals
            </a>
        </div>
    </div>

    <script>
        document.getElementById("search").addEventListener("keyup", function() {{
            const term = this.value.toLowerCase();
            document.querySelectorAll("#userTable tr").forEach(row => {{
                row.style.display = row.textContent.toLowerCase().includes(term) ? "" : "none";
            }});
        }});
    </script>
    </body>
    </html>
    """

@app.get("/admin/logout")
async def admin_logout():
    return RedirectResponse("/admin/login")

@app.get("/admin/user/{username}", response_class=HTMLResponse)
async def admin_user_detail(username: str):
    return RedirectResponse("/admin/dashboard")

@app.get("/admin/transactions", response_class=HTMLResponse)
async def admin_transactions():
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT d.id, d.username, d.amount, d.status, d.timestamp, d.proof_image 
        FROM deposits d ORDER BY d.id DESC
    """)
    deposits = cursor.fetchall()
    
    cursor.execute("""
        SELECT w.id, w.username, w.amount, w.bank_name, w.account_number, w.status, w.timestamp 
        FROM withdrawals w ORDER BY w.id DESC
    """)
    withdrawals = cursor.fetchall()
    
    dep_rows = "".join([f"""
        <tr class="border-b border-gray-800">
            <td class="py-4">@{row[1]}</td>
            <td class="py-4 font-bold">₦{row[2]:,.0f}</td>
            <td class="py-4">{row[4]}</td>
            <td class="py-4 {'text-yellow-400' if row[3]=='pending' else 'text-green-400'}">{row[3]}</td>
            <td class="py-4">
                {'<a href="/admin/approve/deposit/' + str(row[0]) + '" class="text-green-400">Approve</a>' if row[3] == 'pending' else 'Approved'}
            </td>
        </tr>
    """ for row in deposits])
    
    wd_rows = "".join([f"""
        <tr class="border-b border-gray-800">
            <td class="py-4">@{row[1]}</td>
            <td class="py-4 font-bold">₦{row[2]:,.0f}</td>
            <td class="py-4">{row[3]} - {row[4]}</td>
            <td class="py-4 {'text-yellow-400' if row[5]=='pending' else 'text-green-400'}">{row[5]}</td>
            <td class="py-4">
                {'<a href="/admin/approve/withdraw/' + str(row[0]) + '" class="text-green-400">Approve</a>' if row[5] == 'pending' else 'Approved'}
            </td>
        </tr>
    """ for row in withdrawals])
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Transactions - Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white p-8">
        <h1 class="text-4xl font-bold text-green-400 mb-10">Transaction Management</h1>
        <h2 class="text-2xl mb-4">Pending Deposits</h2>
        <table class="w-full mb-12">{dep_rows or '<p>No deposits</p>'}</table>
        <h2 class="text-2xl mb-4">Pending Withdrawals</h2>
        <table class="w-full">{wd_rows or '<p>No withdrawals</p>'}</table>
    </body>
    </html>
    """

@app.get("/admin/approve/deposit/{dep_id}")
async def approve_deposit(dep_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT username, amount FROM deposits WHERE id=?", (dep_id,))
    row = cursor.fetchone()
    if row:
        username, amount = row
        cursor.execute("UPDATE users SET balance = balance + ? WHERE username=?", (amount, username))
        cursor.execute("UPDATE deposits SET status='approved', approved_at=? WHERE id=?", 
                      (datetime.now(NIGERIA_TZ).isoformat(), dep_id))
        conn.commit()
    return RedirectResponse("/admin/transactions")

@app.get("/admin/approve/withdraw/{wd_id}")
async def approve_withdraw(wd_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT username, amount FROM withdrawals WHERE id=?", (wd_id,))
    row = cursor.fetchone()
    if row:
        username, amount = row
        cursor.execute("UPDATE users SET balance = balance - ? WHERE username=? AND balance >= ?", 
                      (amount, username, amount))
        cursor.execute("UPDATE withdrawals SET status='approved', approved_at=? WHERE id=?", 
                      (datetime.now(NIGERIA_TZ).isoformat(), wd_id))
        conn.commit()
    return RedirectResponse("/admin/transactions")

# ================== END ==================
if __name__ == "__main__":
    print("🚀 HeroStake AI Running → http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)