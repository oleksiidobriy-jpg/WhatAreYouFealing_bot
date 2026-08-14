#!/usr/bin/env python3
"""
Надсилає в Telegram питання "що ти зараз відчуваєш" 5-7 разів на день
у випадковий час у вікні 09:00-21:00 за Дубліном.

План на день виводиться детерміновано з дати через sha256, тому всі запуски
одного дня бачать однаковий розклад.

GitHub Actions не гарантує запуск за розкладом і під навантаженням викидає
частину запусків. Тому скрипт тримає state.json зі списком уже опрацьованих
слотів: якщо запуск пропустили, наступний живий добиває борг.
"""

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

# ---------- налаштування ----------

TZ = ZoneInfo(os.environ.get("TZ_NAME", "Europe/Dublin"))

START_HOUR = 9              # включно, за Дубліном
END_HOUR = 21               # не включно, тобто останній слот 20:45
SLOT_MINUTES = 15
COUNTS_PER_DAY = (5, 6, 7)  # скільки повідомлень на день, обирається випадково
MIN_GAP_MINUTES = 60        # мінімальний розрив між повідомленнями
MAX_LATE_MINUTES = 90       # наскільки пізно ще не соромно надолужити пропущене

STATE_FILE = "state.json"
NAME = "Таня"

MESSAGES = [
    "Привет, {name}. Что ты сейчас чувствуешь?",
    "{name}, привет. Какие чувства у тебя прямо сейчас?",
    "Привет. Остановись на секунду — что ты сейчас чувствуешь?",
    "{name}, что сейчас внутри?",
    "Привет, {name}. Назови одним словом, что чувствуешь сейчас.",
    "Что ты чувствуешь в эту минуту, {name}?",
    "{name}, привет. Какое чувство сейчас самое сильное?",
    "Привет. Как ты сейчас себя чувствуешь?",
    "{name}, что происходит внутри прямо сейчас?",
    "Привет, {name}. Что чувствуешь в этот момент?",
]

# ---------- план на день ----------


def digest(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest(), 16)


def all_slots() -> list[int]:
    return [
        h * 60 + m
        for h in range(START_HOUR, END_HOUR)
        for m in range(0, 60, SLOT_MINUTES)
    ]


def plan_for(day: str) -> list[int]:
    count = COUNTS_PER_DAY[digest(day, "count") % len(COUNTS_PER_DAY)]
    ranked = sorted(all_slots(), key=lambda s: digest(day, "slot", s))

    chosen: list[int] = []
    for gap in range(MIN_GAP_MINUTES, SLOT_MINUTES - 1, -SLOT_MINUTES):
        chosen = []
        for slot in ranked:
            if all(abs(slot - c) >= gap for c in chosen):
                chosen.append(slot)
            if len(chosen) == count:
                return sorted(chosen)
    return sorted(chosen)


def message_for(day: str, slot: int) -> str:
    return MESSAGES[digest(day, "msg", slot) % len(MESSAGES)].format(name=NAME)


def fmt(slot: int) -> str:
    return f"{slot // 60:02d}:{slot % 60:02d}"


# ---------- стан ----------


def load_state(day: str) -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("day") == day:
            return state
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"day": day, "handled": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------- відправка ----------


def send(text: str) -> None:
    token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        print("telegram:", resp.status, resp.read().decode()[:200])


def main() -> None:
    now = datetime.now(TZ)
    day = now.strftime("%Y-%m-%d")
    plan = plan_for(day)

    if "--plan" in sys.argv:
        print(f"{day}: {len(plan)} шт -> {', '.join(fmt(s) for s in plan)}")
        return

    now_min = now.hour * 60 + now.minute
    state = load_state(day)
    handled = set(state["handled"])

    passed = [s for s in plan if s <= now_min]
    pending = [s for s in passed if s not in handled]

    print(f"зараз {now:%H:%M} | план {[fmt(s) for s in plan]} | борг {[fmt(s) for s in pending]}")

    if os.environ.get("FORCE") == "true":
        send(message_for(day, now_min - now_min % SLOT_MINUTES))
        return

    # усе, що минуло, вважаємо опрацьованим незалежно від результату,
    # інакше старий борг висітиме вічно
    state["handled"] = sorted(set(passed))
    save_state(state)

    if not pending:
        print("боргу немає, виходимо")
        return

    slot = max(pending)  # найсвіжіший пропущений
    late = now_min - slot
    if late > MAX_LATE_MINUTES:
        print(f"слот {fmt(slot)} протермінований на {late} хв, пропускаємо")
        return

    print(f"надсилаємо за слот {fmt(slot)}, запізнення {late} хв")
    send(message_for(day, slot))


if __name__ == "__main__":
    main()
