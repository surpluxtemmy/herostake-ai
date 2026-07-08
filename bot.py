import pyautogui
import time
import logging
import cv2
import numpy as np
import requests
import sqlite3
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ================= CONFIG =================
PLATFORM_API = "http://127.0.0.1:8000"
EXTRA_PROFIT_PERCENT = 0.30

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

pyautogui.FAILSAFE = True

last_active_count = 0
last_total_base = 0

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

def click_digit(digit):
    pos = DIGITS.get(str(digit))
    if pos:
        pyautogui.click(pos)
        time.sleep(0.2)

def is_auto_cashout_on():
    try:
        x, y = AUTO_CASHOUT_BUTTON
        region = (x - 8, y - 8, 16, 16)
        screenshot = pyautogui.screenshot(region=region)
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_green = np.array([35, 70, 70])
        upper_green = np.array([85, 255, 255])
        mask = cv2.inRange(hsv, lower_green, upper_green)
        green_ratio = (cv2.countNonZero(mask) / (region[2] * region[3])) * 100
        return green_ratio > 25
    except:
        return False

def get_bet_button_color_status():
    try:
        x, y = BET_BUTTON
        region = (x - 30, y - 25, 60, 50)
        screenshot = pyautogui.screenshot(region=region)
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        lower_green = np.array([40, 50, 50])
        upper_green = np.array([85, 255, 255])
        green_ratio = (cv2.countNonZero(cv2.inRange(hsv, lower_green, upper_green)) / (region[2] * region[3])) * 100
        
        lower_yellow = np.array([20, 80, 80])
        upper_yellow = np.array([35, 255, 255])
        yellow_ratio = (cv2.countNonZero(cv2.inRange(hsv, lower_yellow, upper_yellow)) / (region[2] * region[3])) * 100
        
        lower_grey = np.array([0, 0, 20])
        upper_grey = np.array([180, 60, 110])
        grey_ratio = (cv2.countNonZero(cv2.inRange(hsv, lower_grey, upper_grey)) / (region[2] * region[3])) * 100
        
        print(f"🔘 Button - Green: {green_ratio:.1f}% | Yellow: {yellow_ratio:.1f}% | Grey: {grey_ratio:.1f}%")
        
        if green_ratio > 40:
            return "GREEN"
        elif yellow_ratio > 35:
            return "YELLOW"
        elif grey_ratio > 45:
            return "GREY"
        else:
            return "UNKNOWN"
    except:
        return "ERROR"

def is_multiplier_still_visible():
    try:
        screenshot = pyautogui.screenshot(region=MIDDLE_MULTIPLIER_REGION)
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
        return cv2.countNonZero(thresh) > 120
    except:
        return False

def is_green_result():
    try:
        screenshot = pyautogui.screenshot(region=HISTORY_REGION)
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_green = np.array([30, 40, 40])
        upper_green = np.array([100, 255, 255])
        mask_green = cv2.inRange(hsv, lower_green, upper_green)
        green_ratio = cv2.countNonZero(mask_green) / (img.shape[0] * img.shape[1]) * 100
        print(f"🟢 Green detection ratio: {green_ratio:.2f}%")
        return green_ratio > 5
    except Exception as e:
        print(f"Detection error: {e}")
        return False

def report_result(username, result, user_bet, capital_before, capital_after):
    try:
        data = {
            "username": username,
            "result": result,
            "user_bet": user_bet,
            "capital_before": capital_before,
            "new_capital": capital_after
        }
        requests.post(f"{PLATFORM_API}/api/bet-result", json=data, timeout=8)
    except:
        pass

def wait_for_bet_button_ready(max_wait=30):
    print("⏳ Waiting for Bet button to turn GREEN...")
    for i in range(max_wait):
        status = get_bet_button_color_status()
        if status == "GREEN":
            print("✅ Bet button is GREEN and ready!")
            time.sleep(1.0)
            return True
        if i % 6 == 0 and i > 0:
            print(f"   Still waiting... ({i}/{max_wait}s)")
        time.sleep(1)
    print("⚠️ Timeout waiting for green button")
    return False

def place_bet(amount):
    print(f"🔵 Placing TOTAL bet: ₦{amount:,}")
    pyautogui.click(BET_AMOUNT_FIELD)
    time.sleep(0.8)
    pyautogui.click(CLEAR_BUTTON)
    time.sleep(0.6)
    
    for char in str(amount):
        click_digit(char)
        time.sleep(0.25)
    
    pyautogui.click(DONE_BUTTON)
    time.sleep(0.8)
    pyautogui.click(BET_BUTTON)
    print("✅ Total Bet placed")

# ================= MAIN BOT =================
print("🚀 HeroStake AI Bot Started | 1.9x Recovery Mode")

total_lost_in_streak = 0
loss_streak = 0
current_bet = 0

while True:
    try:
        active_users = get_active_users()
        current_active_count = len(active_users)

        if current_active_count == 0:
            print("⏳ No active users. Waiting...")
            total_lost_in_streak = 0
            loss_streak = 0
            time.sleep(8)
            continue

        total_base = calculate_total_base(active_users)
        total_capital = calculate_total_capital(active_users)

        if last_active_count > current_active_count and last_active_count > 0:
            ratio_remaining = total_base / last_total_base if last_total_base > 0 else 1
            total_lost_in_streak = int(total_lost_in_streak * ratio_remaining)
            print(f"👤 User left. Adjusting lost amount proportionally → ₦{total_lost_in_streak:,}")

        last_active_count = current_active_count
        last_total_base = total_base

        print(f"👥 Active Users: {current_active_count} | Total Base: ₦{total_base:,} | Total Capital: ₦{total_capital:,}")

        if total_capital <= 0:
            print("🚨 Total Capital exhausted. Stopping.")
            break

        if loss_streak == 0:
            current_bet = total_base
            print(f"🟢 New Round - Betting Base: ₦{current_bet:,}")
        else:
            extra_profit = int(total_base * EXTRA_PROFIT_PERCENT)
            needed_to_recover = total_lost_in_streak + extra_profit
            current_bet = int(needed_to_recover / 0.9)
            print(f"🔄 Recovery Mode | Lost: ₦{total_lost_in_streak:,} + 30% extra → Bet: ₦{current_bet:,}")

        max_allowed = int(total_capital * 0.6)
        if current_bet > max_allowed:
            current_bet = max_allowed
            print(f"⚠️ Bet capped at 60% of total capital: ₦{current_bet:,}")

        if not is_auto_cashout_on():
            print("⛔ Auto Cashout is OFF - Waiting...")
            time.sleep(5)
            continue

        if not wait_for_bet_button_ready(max_wait=30):
            print("⚠️ Could not detect green button, skipping cycle")
            time.sleep(5)
            continue

        if not is_auto_cashout_on():
            print("⛔ Auto Cashout OFF - Aborting")
            time.sleep(3)
            continue

        place_bet(current_bet)

        # ================= POST-BET MONITORING =================
        print("🔍 Waiting for round to start (expecting Yellow)...")
        time.sleep(3)

        status = get_bet_button_color_status()

        if status == "GREY":
            print("🚨 BET HANG DETECTED - Still dark grey after 3 seconds!")
            pyautogui.click(BET_BUTTON)
            time.sleep(3)
            continue

        if status == "GREEN":
            print("⚡ Quick return to GREEN → Instant Loss (1.0x ~ 1.02x)")
            is_win = False
        else:
            print("✅ Round started (Yellow detected), continuing monitoring...")
            time.sleep(5)
            hang_checks = 0
            while is_multiplier_still_visible() and hang_checks < 5:
                hang_checks += 1
                time.sleep(5)
            is_win = is_green_result()

        if is_win:
            total_lost_in_streak = 0
            loss_streak = 0
            print("✅ WIN - Recovery Reset")
        else:
            total_lost_in_streak += current_bet
            loss_streak += 1
            print(f"❌ LOSS - Total Lost Now: ₦{total_lost_in_streak:,} | Streak: {loss_streak}")

        # Streak sleep logic
        if loss_streak == 10:
            print("😴 Loss streak of 10 reached. Sleeping for 1 minute...")
            time.sleep(60)
        elif loss_streak == 12:
            print("😴 Loss streak of 12 reached. Sleeping for 2 minutes...")
            time.sleep(120)
        elif loss_streak == 13:
            print("😴 Loss streak of 13 reached. Sleeping for 3 minutes...")
            time.sleep(180)

        # Distribute results
        for username, balance, base_bet, take_profit, stop_loss, current_profit in active_users:
            if balance <= 0 or current_profit >= take_profit or current_profit <= -stop_loss:
                continue

            ratio = base_bet / total_base if total_base > 0 else 0
            user_bet = int(current_bet * ratio)

            if is_win:
                user_profit = int(user_bet * 0.9)
                new_capital = balance + user_profit
            else:
                new_capital = balance - user_bet

            report_result(username, "win" if is_win else "loss", user_bet, balance, new_capital)

        time.sleep(6)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(10)