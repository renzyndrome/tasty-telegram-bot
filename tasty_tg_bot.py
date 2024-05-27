import logging
import os
import gspread
import re
from collections import deque
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set logging level for less important modules to WARNING
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)

# Load environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEET_CREDENTIALS = os.getenv("GOOGLE_SHEET_CREDENTIALS")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")

# Google Sheets setup
scope = [
    "https://spreadsheets.google.com/feeds",
    'https://www.googleapis.com/auth/spreadsheets',
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(GOOGLE_SHEET_KEY).sheet1

# Queue to hold incoming messages
message_queue = deque()

# Define extraction functions
def extract_name(text):
    match = re.search(r'Summary of Tips and VIPs for\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_date_shift(text):
    match = re.search(r'(\w+ \d+, \d{4}):\s*(\d+[AP]M-\d+[AP]M PST)', text, re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return None

def extract_shift_hours(text):
    match = re.search(r'Shift\s*\((\d+)\s*hours\)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_creator(text):
    match = re.search(r'Creator\s*:\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_vip_tips(text):
    matches = re.findall(r'\$(\d+)\s*TIP\s*from\s*@\w+', text, re.IGNORECASE)
    if matches:
        return ', '.join(matches)
    return None

def extract_ppvs(text):
    matches = re.findall(r'\$(\d+)\s*PPV PAID\s*from\s*@\w+', text, re.IGNORECASE)
    if matches:
        return ', '.join(matches)
    return None

def extract_total_gross_sale(text):
    match = re.search(r'TOTAL GROSS SALE:\s*\$\s*(\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_total_net_sale(text):
    match = re.search(r'TOTAL NET SALE:\s*\$\s*(\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_dollar_sales(text):
    match = re.search(r'\$ in sales = \$(\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

# Define a few command handlers
async def start(update: Update, context: CallbackContext) -> None:
    logger.info('Received /start command')
    await update.message.reply_text('Hi! I am your bot.')

# Define a function to set a reaction on a message
async def set_reaction(context: CallbackContext, chat_id, message_id, reaction):
    try:
        await context.bot.set_message_reaction(chat_id, message_id, reaction)
        logger.info(f"Reaction set to {reaction} on message {message_id}")
    except Exception as e:
        logger.error(f"Failed to set reaction: {e}")

async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    logger.info(f'Received message: {text}')

    # Check if the message contains the specific phrase
    if 'Summary of Tips and VIPs for' not in text:
        return

    # Extract data from the message text
    name = extract_name(text)
    date_shift = extract_date_shift(text)
    creator = extract_creator(text)
    vip_tips = extract_vip_tips(text)
    ppvs = extract_ppvs(text)
    total_gross_sale = extract_total_gross_sale(text)
    total_net_sale = extract_total_net_sale(text)
    shift_hours = extract_shift_hours(text)
    dollar_sales = extract_dollar_sales(text)

    if not all([name, date_shift, creator, total_gross_sale, total_net_sale, shift_hours, dollar_sales]):
        logger.warning(f'Invalid input format: {text}')
        await update.message.reply_text('Hey! Please format your summary like this!\n👉🏻 https://t.me/c/1811961823/1701 👈🏻')
        return

    # Add message to the queue
    message_queue.append((update.message.chat_id, {
        'name': name,
        'date_shift': date_shift,
        'creator': creator,
        'vip_tips': vip_tips,
        'ppvs': ppvs,
        'total_gross_sale': total_gross_sale,
        'total_net_sale': total_net_sale,
        'shift_hours': shift_hours,
        'dollar_sales': dollar_sales
    }))

    # React with a specific emoji
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    try:
        await context.bot.set_message_reaction(chat_id, message_id, reaction="🎉")
        logger.info(f"Reaction on message {message_id}")
    except Exception as e:
        logger.error(f"Failed to set reaction: {e}")

async def process_queue(context: CallbackContext) -> None:
    while message_queue:
        chat_id, data = message_queue.popleft()

        # Log extracted data
        logger.info(f'Extracted data: {data}')

        try:
            # Add a new row to the Google Sheet
            sheet.append_row([
                data['date_shift'],
                data['name'],
                data['shift_hours'],
                data['creator'],
                data['vip_tips'],
                data['ppvs'],
                data['total_gross_sale'],
                data['total_net_sale'],
                data['dollar_sales']
            ])
            logger.info('Data successfully appended to the Google Sheet.')

        except Exception as e:
            logger.error(f'Failed to append data to the Google Sheet: {e}')

def main() -> None:
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))

    # on non-command i.e message - handle the message
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the process_queue function every 10 seconds
    job_queue = application.job_queue
    job_queue.run_repeating(process_queue, interval=10, first=10)

    # Run the bot until you press Ctrl-C
    application.run_polling()

if __name__ == '__main__':
    main()
