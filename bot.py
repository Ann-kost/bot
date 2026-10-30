
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()
engine = create_engine("sqlite:///hockey_bot.db")
Session = sessionmaker(bind=engine)

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, index=True)
    team_name = Column(String, default="Моя команда")
    coins = Column(Integer, default=1000)
    # Состав хранится в JSON или отдельной таблице, для упрощения используем строку
    lineup = Column(String, default="")  # сохраняем card_id через запятую

class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    name = Column(String)
    position = Column(String)  # C, LW, RW, D, G
    overall = Column(Integer)  # общий рейтинг 50-99
    rarity = Column(String)    # common, rare, epic, legendary

class MatchLog(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    result = Column(String)  # "win"/"loss"
    score = Column(String)   # "3:2"
    log = Column(String)     # текстовая трансляция

Base.metadata.create_all(engine)
import random

def simulate_match(user_cards, opponent_strength=65):
    """
    user_cards: список объектов Card
    Возвращает (лог, счёт, победа)
    """
    user_power = sum(c.overall for c in user_cards) / max(len(user_cards), 1)
    opp_power = opponent_strength + random.randint(-10, 10)

    log_lines = ["🏒 Матч начался!", f"Сила вашей команды: {user_power:.0f}"]
    user_goals = opp_goals = 0
    events = [
        ("Атака по левому флангу...", 3),
        ("Мощный бросок от синей линии!", 5),
        ("Выход один на один!", 8),
        ("Контратака!", 4),
    ]

    for period in range(3):  # 3 периода
        log_lines.append(f"\n--- {period+1}-й период ---")
        for _ in range(3):  # 3 события за период
            desc, weight = random.choice(events)
            # Вероятность гола зависит от силы
            goal_chance = (user_power - opp_power + 50) / 100 + weight / 50
            if random.random() < goal_chance * 0.3:
                user_goals += 1
                log_lines.append(f"⚡ {desc} ГОЛ! {user_goals}:{opp_goals}")
            else:
                log_lines.append(f"  {desc} Вратарь спасает.")
            # Ответная атака соперника
            if random.random() < (opp_power / 200):
                opp_goals += 1
                log_lines.append(f"😔 Соперник забивает. {user_goals}:{opp_goals}")

    win = user_goals > opp_goals
    log_lines.append(f"\n🏁 Итог: {user_goals}:{opp_goals} — {'Победа!' if win else 'Поражение'}")
    return "\n".join(log_lines), f"{user_goals}:{opp_goals}", win
import random

NAMES = ["Овечкин", "Малкин", "Кучеров", "Панарин", "Бобровский", "Василевский",
         "Макдэвид", "Драйзайтль", "Пастрняк", "Маршан"]
POSITIONS = ["C", "LW", "RW", "D", "G"]
RARITIES = [("common", 60), ("rare", 25), ("epic", 10), ("legendary", 5)]

def generate_card(user_id):
    name = random.choice(NAMES)
    pos = random.choice(POSITIONS)
    rarity = random.choices([r[0] for r in RARITIES], weights=[r[1] for r in RARITIES])[0]
    base = {"common": 55, "rare": 68, "epic": 80, "legendary": 92}[rarity]
    overall = base + random.randint(0, 7)
    return Card(user_id=user_id, name=name, position=pos, overall=overall, rarity=rarity)

def open_pack(user_id, pack_type="standard"):
    """Возвращает список карточек в наборе"""
    count = 3 if pack_type == "standard" else 5
    return [generate_card(user_id) for _ in range(count)]
from telegram import LabeledPrice

async def send_pack_invoice(update, context, pack_type, stars):
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"Набор карточек ({pack_type})",
        description="Откройте набор и получите игроков для состава!",
        payload=f"pack:{pack_type}",
        provider_token="",       # Stars не требует провайдера
        currency="XTR",          # Telegram Stars
        prices=[LabeledPrice("Набор", stars)],
        start_parameter="buy_pack"
    )

BOT_TOKEN = "9211063867:AAF1TXUihmjdgOWqqCJn44uIrot4ZrxX4K0"
async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("🎴 Открыть набор (50⭐)", callback_data="pack_standard")],
        [InlineKeyboardButton("📋 Мой состав", callback_data="my_lineup")],
        [InlineKeyboardButton("🏒 Играть матч", callback_data="play_match")],
    ]
    await update.message.reply_text("Хоккейный бот-менеджер", reply_markup=InlineKeyboardMarkup(keyboard))

async def pack_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    await send_pack_invoice(update, context, "standard", 50)

async def successful_payment(update: Update, context):
    # Здесь открываем набор и сохраняем карточки в БД
    session = Session()
    user_id = update.effective_user.id
    cards = open_pack(user_id, "standard")
    for c in cards:
        session.add(c)
    session.commit()
    msg = "🎉 Вы получили:\n" + "\n".join(f"• {c.name} ({c.position}) OVR {c.overall}" for c in cards)
    await update.message.reply_text(msg)

async def play_match(update: Update, context):
    query = update.callback_query
    await query.answer()
    session = Session()
    user_id = update.effective_user.id
    cards = session.query(Card).filter_by(user_id=user_id).limit(6).all()
    if len(cards) < 3:
        await query.message.reply_text("Нужно минимум 3 карточки. Купите набор!")
        return
    log, score, win = simulate_match(cards)
    await query.message.reply_text(log)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(pack_callback, pattern="pack_standard"))
    app.add_handler(CallbackQueryHandler(play_match, pattern="play_match"))
    app.add_handler(PreCheckoutQueryHandler(lambda u, c: u.pre_checkout_query.answer(ok=True)))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.run_polling()

if __name__ == "__main__":
    main()