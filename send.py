#!/usr/bin/env python3
"""
Шлёт в Telegram вопрос "что ты сейчас чувствуешь" 5-7 раз в день
в случайное время внутри окна 09:00-21:00.

Состояние нигде не хранится: план на день выводится детерминированно
из даты через sha256, поэтому все запуски одного дня видят один и тот же план.

Зависимостей нет, только стандартная библиотека.
"""

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

# ---------- настройки ----------

TZ = ZoneInfo(os.environ.get("TZ_NAME", "Europe/Dublin"))

START_HOUR = 9          # включительно, по Дублину
END_HOUR = 21           # не включительно, т.е. последний слот 20:45
SLOT_MINUTES = 15       # должен совпадать с cron в воркфлоу
COUNTS_PER_DAY = (5, 6, 7)  # сколько сообщений в день, выбирается случайно из этого списка
MIN_GAP_MINUTES = 60     # минимальный разрыв между сообщениями

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

# ---------- логика ----------


def digest(*parts) -> int:
    raw = "|".join(str(p) for p in parts).encode()
    return int(hashlib.sha256(raw).hexdigest(), 16)


def all_slots() -> list[int]:
    """Все возможные слоты дня в минутах от полуночи."""
    return [
        h * 60 + m
        for h in range(START_HOUR, END_HOUR)
        for m in range(0, 60, SLOT_MINUTES)
    ]


def plan_for(day: str) -> list[int]:
    """Выбранные слоты на конкретный день. Одинаковы для всех запусков этого дня."""
    count = COUNTS_PER_DAY[digest(day, "count") % len(COUNTS_PER_DAY)]
    ranked = sorted(all_slots(), key=lambda s: digest(day, "slot", s))

    # если с полным разрывом нужное количество не набирается, постепенно его ослабляем
    for gap in range(MIN_GAP_MINUTES, SLOT_MINUTES - 1, -SLOT_MINUTES):
        chosen: list[int] = []
        for slot in ranked:
            if all(abs(slot - c) >= gap for c in chosen):
                chosen.append(slot)
            if len(chosen) == count:
                return sorted(chosen)

    return sorted(chosen)


def current_slot(now: datetime) -> int:
    return now.hour * 60 + now.minute - now.minute % SLOT_MINUTES


def message_for(day: str, slot: int) -> str:
    return MESSAGES[digest(day, "msg", slot) % len(MESSAGES)].format(name=NAME)


def send(text: str) -> None:
    token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        print("telegram:", resp.status, resp.read().decode()[:200])


def fmt(slot: int) -> str:
    return f"{slot // 60:02d}:{slot % 60:02d}"


def main() -> None:
    now = datetime.now(TZ)
    day = now.strftime("%Y-%m-%d")
    slots = plan_for(day)

    if "--plan" in sys.argv:
        print(f"{day} ({TZ}): {len(slots)} шт -> {', '.join(fmt(s) for s in slots)}")
        return

    slot = current_slot(now)
    print(f"now={now:%H:%M} slot={fmt(slot)} plan={[fmt(s) for s in slots]}")

    if os.environ.get("FORCE") == "true":
        send(message_for(day, slot))
        return

    if slot not in slots:
        print("не мой слот, выходим")
        return

    send(message_for(day, slot))


if __name__ == "__main__":
    main()
