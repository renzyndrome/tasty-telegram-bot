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


# Define extraction functions with enhanced logging
def extract_name(text):
    logger.debug(f'Extracting name from text: {text}')
    match = re.search(r'Summary of Tips and VIPs for\s*(.*)', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        logger.info(f'Extracted name: {name}')
        return name
    logger.warning(f'Failed to extract name from text: {text}')
    return None

def extract_date_shift(text):
    logger.debug(f'Extracting date_shift from text: {text}')
    match = re.search(r'(\w+ \d+, \d{4})\s*[:\-]\s*(\d+[AP]M-\d+[AP]M PST)', text, re.IGNORECASE)
    if match:
        date_shift = f"{match.group(1)} {match.group(2)}"
        logger.info(f'Extracted date_shift: {date_shift}')
        return date_shift
    logger.warning(f'Failed to extract date_shift from text: {text}')
    return None

def extract_shift_hours(text):
    logger.debug(f'Extracting shift_hours from text: {text}')
    match = re.search(r'Shift[:\s]*\(?(\d+)\s*hours?\)?', text, re.IGNORECASE)
    if match:
        shift_hours = match.group(1).strip()
        logger.info(f'Extracted shift_hours: {shift_hours}')
        return shift_hours
    logger.warning(f'Failed to extract shift_hours from text: {text}')
    return None

def extract_creator(text):
    logger.debug(f'Extracting creator from text: {text}')
    match = re.search(r'Creator\s*:\s*(.*)', text, re.IGNORECASE)
    if match:
        creator = match.group(1).strip()
        logger.info(f'Extracted creator: {creator}')
        return creator
    logger.warning(f'Failed to extract creator from text: {text}')
    return None

def extract_vip_tips(text):
    logger.debug(f'Extracting vip_tips from text: {text}')
    match = re.search(r'VIP/Tips:\s*(.*?)\n\n', text, re.IGNORECASE | re.DOTALL)
    if match:
        amounts = re.findall(r'\$(\d+)', match.group(1))
        if amounts:
            vip_tips = ', '.join([f"${amount}" for amount in amounts])
            logger.info(f'Extracted vip_tips: {vip_tips}')
            return vip_tips
    logger.warning(f'Failed to extract vip_tips from text: {text}')
    return None

def extract_ppvs(text):
    logger.debug(f'Extracting ppvs from text: {text}')
    match = re.search(r'PPVs:\s*(.*?)\n\n', text, re.IGNORECASE | re.DOTALL)
    if match:
        amounts = re.findall(r'\$(\d+)', match.group(1))
        if amounts:
            ppvs = ', '.join([f"${amount}" for amount in amounts])
            logger.info(f'Extracted ppvs: {ppvs}')
            return ppvs
    logger.warning(f'Failed to extract ppvs from text: {text}')
    return None

def extract_total_gross_sale(text):
    logger.debug(f'Extracting total_gross_sale from text: {text}')
    match = re.search(r'TOTAL GROSS SALE:\s*\$\s*([\d,]+)', text, re.IGNORECASE)
    if match:
        total_gross_sale = f"${match.group(1).replace(',', '').strip()}"
        logger.info(f'Extracted total_gross_sale: {total_gross_sale}')
        return total_gross_sale
    logger.warning(f'Failed to extract total_gross_sale from text: {text}')
    return None

def extract_total_net_sale(text):
    logger.debug(f'Extracting total_net_sale from text: {text}')
    match = re.search(r'TOTAL NET SALE:\s*\$\s*([\d,]+)', text, re.IGNORECASE)
    if match:
        total_net_sale = f"${match.group(1).replace(',', '').strip()}"
        logger.info(f'Extracted total_net_sale: {total_net_sale}')
        return total_net_sale
    logger.warning(f'Failed to extract total_net_sale from text: {text}')
    return None

def extract_dollar_sales(text):
    logger.debug(f'Extracting dollar_sales from text: {text}')
    match = re.search(r'\$(\d{1,3}(?:,\d{3})*)\s+in\s+sales\s+=\s+\$(\d+)\s+bonus', text, re.IGNORECASE)
    if match:
        dollar_sales = f"${match.group(1).replace(',', '').strip()}"
        bonus = f"${match.group(2).replace(',', '').strip()}"
        logger.info(f'Extracted dollar_sales: {dollar_sales}, bonus: {bonus}')
        return dollar_sales, bonus
    logger.warning(f'Failed to extract dollar_sales and bonus from text: {text}')
    return None, None

async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    logger.info(f'Received message: {text}')

    # Check if the message contains the specific phrase
    if 'Summary of Tips and VIPs for' not in text:
        logger.warning('Message does not contain the specific phrase')
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
    dollar_sales, bonus = extract_dollar_sales(text)

    # Log extracted data for debugging purposes
    logger.info(f'Extracted data: name={name}, date_shift={date_shift}, creator={creator}, '
                f'vip_tips={vip_tips}, ppvs={ppvs}, total_gross_sale={total_gross_sale}, '
                f'total_net_sale={total_net_sale}, shift_hours={shift_hours}, '
                f'dollar_sales={dollar_sales}, bonus={bonus}')

    if not all([name, date_shift, creator, total_gross_sale, total_net_sale, shift_hours, dollar_sales, bonus]):
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
        'dollar_sales': dollar_sales,
        'bonus': bonus
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
                data['dollar_sales'],
                data['bonus']
            ])
            logger.info('Data successfully appended to the Google Sheet.')

        except Exception as e:
            logger.error(f'Failed to append data to the Google Sheet: {e}')

async def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(f'Hello {user.first_name}! Send me your summary of tips and VIPs.')

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