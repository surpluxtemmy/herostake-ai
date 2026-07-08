import pyautogui
import time
import logging
import cv2
import numpy as np
import requests
import sqlite3
import random
from datetime import datetime
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ================= CONFIG =================
PLATFORM_API = "http://127.0.0.1:8000"
NIGERIA_TZ = pytz.timezone("Africa/Lagos")
EXTRA_PROFIT_PERCENT = 0.30

# ================= ANTI-BOT CONFIG =================
HUMANIZE = True  # Set to False to disable human-like behavior (not recommended)
MIN_DELAY = 0.15
MAX_DELAY = 0.45
MOUSE_JITTER = 8  # pixels

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


def human_delay(min_sec=None, max_sec=None):
    """Add realistic human delay"""
    if not HUMANIZE:
        time.sleep(0.1)
        return
    if min_sec is None:
        min_sec = MIN_DELAY
    if max_sec is None:
        max_sec = MAX_DELAY
    time.sleep(random.uniform(min_sec, max_sec))


def human_move_to(x, y, duration=None):
    """Move mouse with slight randomness and natural feel"""
    if not HUMANIZE:
        pyautogui.moveTo(x, y, duration=0.1)
        return
    
    # Add small random offset
    offset_x = random.randint(-MOUSE_JITTER, MOUSE_JITTER)
    offset_y = random.randint(-MOUSE_JITTER, MOUSE_JITTER)
    target_x = x + offset_x
    target_y = y + offset_y
    
    if duration is None:
        duration = random.uniform(0.08, 0.25)
    
    pyautogui.moveTo(target_x, target_y, duration=duration, tween=pyautogui.easeInOutQuad)


def human_click(x, y):
    """Perform human-like click"""
    human_move_to(x, y)
    human_delay(0.05, 0.15)
    pyautogui.click()
    human_delay(0.1, 0.3)


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
        human_click(*pos)


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


def place_bet(amount):
    print(f"🔵 Placing TOTAL bet: ₦{amount:,}")
    
    # Human-like bet placement
    human_click(*BET_AMOUNT_FIELD)
    human_delay(0.8, 1.4)
    
    human_click(*CLEAR_BUTTON)
    human_delay(0.5, 0.9)
    
    amount_str = str(amount)
    for i, char in enumerate(amount_str):
        click_digit(char)
        if i < len(amount_str) - 1:
            human_delay(0.18, 0.38)
        else:
            human_delay(0.25, 0.45)
    
    human_click(*DONE_BUTTON)
    human_delay(0.6, 1.1)
    
    human_click(*BET_BUTTON)
    print("✅ Total Bet placed")


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


# ================= MAIN BOT =================
print("🚀 HeroStake AI Bot Started | 1.9x Recovery Mode | Anti-Detection Enabled")

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
            human_delay(7, 12)
            continue

        total_base = calculate_total_base(active_users)
        total_capital = calculate_total_capital(active_users)

        # Adjust when users leave
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

        # === RECOVERY CALCULATION (1.9x Cashout + 30% Extra Profit) ===
        if loss_streak == 0:
            current_bet = total_base
            print(f"🟢 New Round - Betting Base: ₦{current_bet:,}")
        else:
            extra_profit = int(total_base * EXTRA_PROFIT_PERCENT)
            needed_to_recover = total_lost_in_streak + extra_profit
            current_bet = int(needed_to_recover / 0.9)
            print(f"🔄 Recovery Mode | Lost: ₦{total_lost_in_streak:,} + 30% extra → Bet: ₦{current_bet:,}")

        # Safety cap
        max_allowed = int(total_capital * 0.6)
        if current_bet > max_allowed:
            current_bet = max_allowed
            print(f"⚠️ Bet capped at 60% of total capital: ₦{current_bet:,}")

        if not is_auto_cashout_on():
            human_delay(2.5, 4)
            continue

        place_bet(current_bet)

        # Random wait after placing bet
        human_delay(4.5, 6.5)

        hang_checks = 0
        while is_multiplier_still_visible() and hang_checks < 4:
            hang_checks += 1
            human_delay(4.5, 6)
        
        # Occasional idle movement to look more human
        if random.random() < 0.4:
            pyautogui.moveRel(random.randint(-60, 60), random.randint(-40, 40), duration=0.3)

        is_win = is_green_result()

        if is_win:
            total_lost_in_streak = 0
            loss_streak = 0
            print("✅ WIN - Recovery Reset")
        else:
            total_lost_in_streak += current_bet
            loss_streak += 1
            print(f"❌ LOSS - Total Lost Now: ₦{total_lost_in_streak:,} | Streak: {loss_streak}")

        # ================= STREAK SLEEP LOGIC =================
        if loss_streak == 10:
            print("😴 Loss streak reached. Sleeping for ~1 minute...")
            time.sleep(55 + random.randint(0, 15))
        elif loss_streak == 12:
            print("😴 Loss streak reached. Sleeping for ~2 minutes...")
            time.sleep(110 + random.randint(0, 30))
        elif loss_streak == 13:
            print("😴 Loss streak reached. Sleeping for ~3 minutes...")
            time.sleep(170 + random.randint(0, 40))

        # Distribute result to users
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

        # Random delay between rounds
        human_delay(5, 9)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(10)