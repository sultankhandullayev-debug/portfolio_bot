import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta

# --- 1. НАСТРОЙКИ ---
API_TOKEN = '8200484768:AAEeiQ3DQEKsfJwsT3uUjZfDAjctyzjm-j0'
MY_CHAT_ID = 573018879
JSON_FILE = 'awesome-flash-488610-m0-976189e30fc0.json'
SPREADSHEET_NAME = 'Портфель_таблица'

# База дивидендов
portfolio_div_data = {
    'CVX':  [16.02, 1.63, [3, 6, 9, 12]],
    'AAPL': [14.00, 0.25, [2, 5, 8, 11]],
    'PG':   [27.00, 1.01, [2, 5, 8, 11]],
    'TSM':  [9.00,  0.62, [1, 4, 7, 10]],
    'NVDA': [20.00, 0.01, [3, 6, 9, 12]],
    'MSFT': [7.00,  0.83, [3, 6, 9, 12]],
    'URA':  [70.00, 0.15, [6, 12]],
    'SPYM': [33.00, 0.45, [3, 6, 9, 12]],
    'SCHD': [87.00, 0.75, [3, 6, 9, 12]],
    'V':    [5.07,  0.52, [3, 6, 9, 12]],
}

# ИСПРАВЛЕНО: session передаётся в Bot
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open(SPREADSHEET_NAME)
    return spreadsheet.sheet1, spreadsheet.worksheet("История акций")

def clean_val(val):
    if not val: return 0.0
    cleaned = "".join(str(val).replace('%', '').replace('$', '').replace(',', '.').split())
    try: return float(cleaned)
    except: return 0.0

def get_main_menu():
    buttons = [
        [KeyboardButton(text="📊 Анализ портфеля"), KeyboardButton(text="⚖️ Ребалансировка")],
        [KeyboardButton(text="💰 Дивиденды месяца"), KeyboardButton(text="📅 План на год")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- 3. ПОСТРОЕНИЕ ОТЧЁТОВ ---

def build_portfolio_report(sheet):
    total_val     = sheet.acell('C5').value
    total_profit  = sheet.acell('C7').value
    profit_pct    = sheet.acell('C9').value
    daily_gain    = sheet.acell('C8').value
    daily_pct     = sheet.acell('D8').value
    annual_return = sheet.acell('C10').value

    tickers  = sheet.col_values(3)[19:34]
    pct_col  = sheet.col_values(11)[19:34]
    cash_col = sheet.col_values(20)[19:34]

    perf_list = []
    for i in range(len(tickers)):
        try:
            perf_list.append({'t': tickers[i], 'p': clean_val(pct_col[i]), 'c': clean_val(cash_col[i])})
        except:
            continue

    top_growth = max(perf_list, key=lambda x: x['p'])
    top_cash   = max(perf_list, key=lambda x: x['c'])
    top_loss   = min(perf_list, key=lambda x: x['p'])

    is_pos     = "-" not in str(daily_gain)
    main_emoji = "▲" if is_pos else "▼"
    plus       = "+" if is_pos else ""

    return (
        f"📈 *Статус портфеля:*\n\n"
        f"💵 Стоимость, USD: *{total_val}*\n"
        f"📅 За сегодня: *{main_emoji} {plus}{daily_gain} ({daily_pct})*\n"
        f"🚀 Профит общий: *{total_profit}* ({profit_pct})\n"
        f"📊 Годовая доходность (IRR): {annual_return}\n"
        f"───────────────\n"
        f"🔹 Ядро: {sheet.acell('C14').value}\n"
        f"🟢 Рост: {sheet.acell('C15').value}\n"
        f"🛡 Защита: {sheet.acell('C16').value}\n"
        f"───────────────\n"
        f"🔥 *Лидеры дня:*\n"
        f"▲ Рост: {top_growth['t']} (+{top_growth['p']}%)\n"
        f"💰 Прибыль: {top_cash['t']} (+${top_cash['c']:.2f})\n"
        f"▼ Падение: {top_loss['t']} ({top_loss['p']}%)\n"
    )

def build_rebalance_report(sheet):
    total_value = clean_val(sheet.acell('C5').value)
    targets  = {"Ядро": 40.0, "Рост": 40.0, "Защита": 20.0}
    currents = {
        "Ядро":   clean_val(sheet.acell('C14').value),
        "Рост":   clean_val(sheet.acell('C15').value),
        "Защита": clean_val(sheet.acell('C16').value),
    }
    report = "⚖️ *Ребалансировка:*\n\n"
    for cat, target in targets.items():
        fact     = currents[cat]
        diff_usd = ((target - fact) / 100) * total_value
        action   = f"🛒 Купить: *${diff_usd:,.0f}*" if diff_usd > 0 else f"✅ Перебор: ${abs(diff_usd):,.0f}"
        report  += f"📍 *{cat}* ({target}%)\nФакт: {fact}% | {action}\n\n"
    return report

def build_dividends_report(month):
    months_ru = ["","Январь","Февраль","Март","Апрель","Май","Июнь",
                 "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
    report = f"💰 *Дивиденды на {months_ru[month]}:*\n\n"
    total  = 0
    for ticker, (shares, div, months) in portfolio_div_data.items():
        if month in months:
            payout  = shares * div
            total  += payout
            report += f"🔹 {ticker}: ${payout:.2f}\n"
    report += f"\n───────────────\n💰 *Итого: ${total:.2f}*"
    return report

def build_year_plan_report():
    total_year = sum(sh * d * len(mnts) for t, (sh, d, mnts) in portfolio_div_data.items())
    return f"📅 *План на год:*\n💰 *${total_year:,.2f}*"

# --- 4. ОБРАБОТЧИКИ КНОПОК ---

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("📈 Система мониторинга запущена!", reply_markup=get_main_menu())

@dp.message(F.text == "📊 Анализ портфеля")
async def analysis(m: types.Message):
    try:
        sheet, _ = get_sheets()
        await m.answer(build_portfolio_report(sheet), parse_mode="Markdown")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")

@dp.message(F.text == "⚖️ Ребалансировка")
async def rebalance(m: types.Message):
    try:
        sheet, _ = get_sheets()
        await m.answer(build_rebalance_report(sheet), parse_mode="Markdown")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")

@dp.message(F.text == "💰 Дивиденды месяца")
async def div_month(m: types.Message):
    month = datetime.now().month
    await m.answer(build_dividends_report(month), parse_mode="Markdown")

@dp.message(F.text == "📅 План на год")
async def year_plan(m: types.Message):
    await m.answer(build_year_plan_report(), parse_mode="Markdown")

# --- 5. ФОНОВЫЕ ЗАДАЧИ ---

async def background_tasks():
    daily_sent_date = None
    alert_until     = None

    while True:
        now   = datetime.now()
        today = now.date()

        try:
            sheet, hist_sheet = get_sheets()

            # АЛЕРТ ±2%
            if alert_until is None or datetime.now() > alert_until:
                pct_raw = sheet.acell('D8').value
                pct_val = clean_val(pct_raw)
                if abs(pct_val) >= 2.0:
                    trend = "ВЗЛЕТЕЛ ▲" if pct_val > 0 else "УПАЛ ▼"
                    await bot.send_message(
                        MY_CHAT_ID,
                        f"⚠️ *Внимание!*\nПортфель {trend} на *{pct_raw}*!",
                        parse_mode="Markdown"
                    )
                    alert_until = datetime.now() + timedelta(hours=4)

            # ЕЖЕДНЕВНЫЙ ДАЙДЖЕСТ в 09:00 по Алматы
            if now.hour == 9 and daily_sent_date != today:
                daily_sent_date = today

                await bot.send_message(MY_CHAT_ID, build_portfolio_report(sheet), parse_mode="Markdown")
                await asyncio.sleep(2)
                await bot.send_message(MY_CHAT_ID, build_rebalance_report(sheet), parse_mode="Markdown")
                await asyncio.sleep(2)
                await bot.send_message(MY_CHAT_ID, build_dividends_report(now.month), parse_mode="Markdown")
                await asyncio.sleep(2)
                await bot.send_message(MY_CHAT_ID, build_year_plan_report(), parse_mode="Markdown")

            # ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ (суббота 09:00)
            if now.weekday() == 5 and now.hour == 9 and now.minute < 1:
                current_val_str  = sheet.acell('C5').value
                current_val      = clean_val(current_val_str)
                all_records      = hist_sheet.get_all_values()

                if len(all_records) > 1:
                    last_val         = clean_val(all_records[-1][1])
                    diff             = current_val - last_val
                    trend            = "▲" if diff >= 0 else "▼"
                    portfolio_return = (current_val - last_val) / last_val if last_val != 0 else 0
                    spy_return       = clean_val(sheet.acell('F7').value)
                    diff_vs_market   = portfolio_return - spy_return
                    action           = "опередил" if diff_vs_market >= 0 else "отстал от"

                    await bot.send_message(MY_CHAT_ID, (
                        f"🗓 *Недельный отчёт:*\n"
                        f"💰 Стоимость: {current_val_str}\n"
                        f"{trend} Изменение: *${diff:,.2f}*\n\n"
                        f"⚖️ *vs S&P 500:*\n"
                        f"Ты {action} рынка на *{abs(diff_vs_market)*100:.2f}%*."
                    ), parse_mode="Markdown")

                hist_sheet.append_row([str(now.date()), current_val_str])
                await asyncio.sleep(61)

        except Exception as e:
            print(f"[{datetime.now()}] Ошибка фона: {e}")

        await asyncio.sleep(120)

# --- 6. ЗАПУСК ---

async def main():
    asyncio.create_task(background_tasks())
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
    except Exception as e:
        print(f"Критическая ошибка: {e}")