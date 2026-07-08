import pyautogui
import time
import logging
import cv2
import numpy as np
import requests
import sqlite3
import random
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ================= CONFIG =================
PLATFORM_API = "http://127.0.0.1:8000"
EXTRA_PROFIT_PERCENT = 0.10

# ================= ANTI-BOT CONFIG =================
MIN_DELAY = 0.25
MAX_DELAY = 1.3
CLICK_OFFSET_RANGE = 7
MOUSE_WIGGLE = True
HUMAN_PAUSE_CHANCE = 0.4

pyautogui.FAILSAFE = True

# ================= COORDINATES =================
BET_AMOUNT_FIELD = (567, 640)
CLEAR_BUTTON = (741, 710)
DONE_BUTTON = (815, 693)
BET_BUTTON = (754, 675)
AUTO_CASHOUT_BUTTON = (752, 589)

HISTORY_REGION = (485, 128, 60, 32)
MIDDLE_MULTIPLIER_REGION = (569, 347, 200, 100)

DIGITS = {
    '0': (614, 708), '1': (505, 671), '2': (542, 672), '3': (573, 670),
    '4': (613, 673), '5': (644, 670), '6': (686, 673), '7': (507, 704),
    '8': (541, 708), '9': (576, 703)
}

last_active_count = 0
last_total_base = 0

# ================= DB FUNCTIONS =================
def get_active_users():
    try:
        conn = sqlite3.connect("platform.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT username, balance, base_bet, take_profit, stop_loss, current_profit 
            FROM users 
            WHERE joined_session = 1 AND base_bet > 0
        """)
        users = cursor.fetchall()
        conn.close()
        return users
    except Exception as e:
        print(f"DB Error: {e}")
        return []

def calculate_total_base(users):
    return sum(user[2] for user in users)

def calculate_total_capital(users):
    return sum(user[1] for user in users)

# ================= ANTI-BOT HELPERS =================
def random_delay(min_sec=0.25, max_sec=1.3):
    time.sleep(random.uniform(min_sec, max_sec))

def human_click(x, y):
    offset_x = random.randint(-CLICK_OFFSET_RANGE, CLICK_OFFSET_RANGE)
    offset_y = random.randint(-CLICK_OFFSET_RANGE, CLICK_OFFSET_RANGE)
    pyautogui.moveTo(x + offset_x, y + offset_y, duration=random.uniform(0.08, 0.25))
    pyautogui.click()
    if MOUSE_WIGGLE and random.random() < 0.45:
        pyautogui.moveRel(random.randint(-6, 6), random.randint(-5, 5), duration=0.1)
    random_delay(0.15, 0.55)

def click_digit(digit):
    pos = DIGITS.get(str(digit))
    if pos:
        human_click(pos[0], pos[1])
        random_delay(0.12, 0.38)

def random_mouse_wiggle():
    if random.random() < 0.55:
        x, y = pyautogui.position()
        pyautogui.moveTo(x + random.randint(-35, 35), y + random.randint(-25, 25), 
                        duration=random.uniform(0.15, 0.4))

# ================= DETECTION =================
def is_auto_cashout_on():
    try:
        x, y = AUTO_CASHOUT_BUTTON
        region = (x - 10, y - 10, 22, 22)
        screenshot = pyautogui.screenshot(region=region)
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([35, 70, 70]), np.array([85, 255, 255]))
        green_ratio = (cv2.countNonZero(mask) / (region[2] * region[3])) * 100
        return green_ratio > 25
    except:
        return False

def place_bet(amount):
    print(f"🔵 Placing TOTAL bet: ₦{amount:,}")
    human_click(*BET_AMOUNT_FIELD)
    random_delay(0.7, 1.3)
    human_click(*CLEAR_BUTTON)
    random_delay(0.5, 0.9)
    
    for i, char in enumerate(str(amount)):
        click_digit(char)
        if i < len(str(amount)) - 1:
            random_delay(0.18, 0.42)
    
    human_click(*DONE_BUTTON)
    random_delay(0.6, 1.0)
    human_click(*BET_BUTTON)
    print("✅ Total Bet placed")

def is_multiplier_still_visible():
    try:
        screenshot = pyautogui.screenshot(region=MIDDLE_MULTIPLIER_REGION)
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 155, 255, cv2.THRESH_BINARY)
        return cv2.countNonZero(thresh) > 110
    except:
        return False

def is_green_result():
    """Improved result detection with multiple samples"""
    for attempt in range(6):  # Try up to 6 times
        try:
            screenshot = pyautogui.screenshot(region=HISTORY_REGION)
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask_green = cv2.inRange(hsv, np.array([30, 40, 40]), np.array([100, 255, 255]))
            green_ratio = cv2.countNonZero(mask_green) / (img.shape[0] * img.shape[1]) * 100
            
            print(f"🟢 Result check {attempt+1}/6 - Green ratio: {green_ratio:.2f}%")
            
            if green_ratio > 8:   # Slightly increased threshold for reliability
                return True
            if green_ratio < 2 and attempt >= 2:
                return False
        except:
            pass
        random_delay(1.2, 2.5)
    return False  # Default to loss if uncertain

def report_result(username, result, user_bet, capital_before, capital_after):
    try:
        data = {"username": username, "result": result, "user_bet": user_bet,
                "capital_before": capital_before, "new_capital": capital_after}
        requests.post(f"{PLATFORM_API}/api/bet-result", json=data, timeout=8)
    except:
        pass

# ================= MAIN BOT =================
print("🚀 HeroStake AI Bot Started | 1.1x Recovery + Anti-Bot v2")

total_lost_in_streak = 0
loss_streak = 0
current_bet = 0

while True:
    try:
        active_users = get_active_users()
        current_active_count = len(active_users)

        if current_active_count == 0:
            print("⏳ No active users. Waiting...")
            random_delay(8, 13)
            continue

        total_base = calculate_total_base(active_users)
        total_capital = calculate_total_capital(active_users)

        if last_active_count > current_active_count and last_active_count > 0:
            ratio_remaining = total_base / last_total_base if last_total_base > 0 else 1
            total_lost_in_streak = int(total_lost_in_streak * ratio_remaining)

        last_active_count = current_active_count
        last_total_base = total_base

        print(f"👥 Active: {current_active_count} | Base: ₦{total_base:,} | Capital: ₦{total_capital:,}")

        if total_capital <= 0:
            print("🚨 Total Capital exhausted.")
            break

        # === RECOVERY CALCULATION ===
        if loss_streak == 0:
            current_bet = total_base
            print(f"🟢 New Round - Betting Base: ₦{current_bet:,}")
        else:
            extra_profit = int(total_base * EXTRA_PROFIT_PERCENT)
            needed_to_recover = total_lost_in_streak + extra_profit
            current_bet = needed_to_recover * 10
            print(f"🔄 Recovery Mode | Lost: ₦{total_lost_in_streak:,} → Bet: ₦{current_bet:,}")

        # Safety cap
        if current_bet > int(total_capital * 0.6):
            current_bet = int(total_capital * 0.6)

        if not is_auto_cashout_on():
            random_delay(2.5, 4)
            continue

        place_bet(current_bet)

        # === WAIT FOR ROUND TO FINISH ===
        print("⏳ Waiting for round to complete...")
        for _ in range(12):  # Max ~30-40 seconds wait
            if not is_multiplier_still_visible():
                break
            random_delay(2.5, 4.0)

        # === CHECK RESULT WITH IMPROVED TIMING ===
        print("🔍 Checking result...")
        is_win = is_green_result()

        if is_win:
            total_lost_in_streak = 0
            loss_streak = 0
            print("✅ WIN - Recovery Reset")
        else:
            total_lost_in_streak += current_bet
            loss_streak += 1
            print(f"❌ LOSS - Total Lost: ₦{total_lost_in_streak:,} | Streak: {loss_streak}")

        # Streak sleep
        if loss_streak == 1:
            time.sleep(random.randint(50, 85))
        elif loss_streak == 2:
            time.sleep(random.randint(120, 170))
        elif loss_streak >= 3:
            time.sleep(random.randint(220, 350))

        # Distribute to users
        for username, balance, base_bet, take_profit, stop_loss, current_profit in active_users:
            if balance <= 0 or current_profit >= take_profit or current_profit <= -stop_loss:
                continue
            ratio = base_bet / total_base if total_base > 0 else 0
            user_bet = int(current_bet * ratio)
            new_capital = balance + int(user_bet * 0.1) if is_win else balance - user_bet
            report_result(username, "win" if is_win else "loss", user_bet, balance, new_capital)

        random_delay(5, 9)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
        break
    except Exception as e:
        print(f"Error: {e}")
        random_delay(8, 15)