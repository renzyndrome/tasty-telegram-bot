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
    match = re.search(r'Summary of Tips and VIPs for[:\s]*(.*)', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        logger.info(f'Extracted name: {name}')
        return name
    logger.warning(f'Failed to extract name from text: {text}')
    return None

def extract_date(text):
    logger.debug(f'Extracting date from text: {text}')
    match = re.search(r'(\d{2}/\d{2}/\d{4})|(\w+ \d+, \d{4})', text)
    if match:
        date = match.group(0).strip()
        logger.info(f'Extracted date: {date}')
        return date
    logger.warning(f'Failed to extract date from text: {text}')
    return None

def extract_shift(text):
    logger.debug(f'Extracting shift from text: {text}')
    match = re.search(r'(\d{1,2}[AP]M) (to|-|–) (\d{1,2}[AP]M PST)', text)
    if match:
        shift = f"{match.group(1)} to {match.group(3)}"
        logger.info(f'Extracted shift: {shift}')
        return shift
    logger.warning(f'Failed to extract shift from text: {text}')
    return None

def extract_shift_hours(text):
    logger.debug(f'Extracting shift hours from text: {text}')
    match = re.search(r'Shift[:\s]*\(?(\d+)\s*hours?\)?', text, re.IGNORECASE)
    if match:
        shift_hours = match.group(1).strip()
        logger.info(f'Extracted shift hours: {shift_hours}')
        return shift_hours
    logger.warning(f'Failed to extract shift hours from text: {text}')
    return None


def extract_creator(text):
    logger.debug(f'Extracting creator from text: {text}')
    match = re.search(r'Creator\s*:\s*(.*?)\s*(?=VIP/Tips:|PPVs:|TOTAL)', text, re.IGNORECASE)
    if match:
        creator = match.group(1).strip()
        logger.info(f'Extracted creator: {creator}')
        return creator
    logger.warning(f'Failed to extract creator from text: {text}')
    return None

def extract_vip_tips(text):
    logger.debug(f'Extracting VIP/tips from text: {text}')
    matches = re.findall(r'\$([\d,]+)\s*(?:TIP|from|@)', text, re.IGNORECASE)
    if matches:
        amounts = [f"${amount.replace(',', '')}" for amount in matches]
        vip_tips = ', '.join(amounts)
        logger.info(f'Extracted VIP/tips amounts: {vip_tips}')
        return vip_tips
    logger.warning(f'Failed to extract VIP/tips from text: {text}')
    return None

def extract_ppvs(text):
    logger.debug(f'Extracting PPVs from text: {text}')
    matches = re.findall(r'\$([\d,]+)\s*(?:PPV|from|@)', text, re.IGNORECASE)
    if matches:
        amounts = [f"${amount.replace(',', '')}" for amount in matches]
        ppvs = ', '.join(amounts)
        logger.info(f'Extracted PPV amounts: {ppvs}')
        return ppvs
    logger.warning(f'Failed to extract PPVs from text: {text}')
    return None



def extract_totals(text):
    logger.debug(f'Extracting totals from text: {text}')
    match = re.search(r'TOTAL GROSS SALE:\s*\$([\d,]+)\s+TOTAL NET SALE:\s*\$([\d,]+)\s+TOTAL BONUS:\s*\$([\d,]+)', text, re.IGNORECASE)
    if match:
        total_gross_sale = f"${match.group(1).replace(',', '').strip()}"
        total_net_sale = f"${match.group(2).replace(',', '').strip()}"
        total_bonus = f"${match.group(3).replace(',', '').strip()}"
        logger.info(f'Extracted totals: Gross Sale: {total_gross_sale}, Net Sale: {total_net_sale}, Bonus: {total_bonus}')
        return total_gross_sale, total_net_sale, total_bonus
    logger.warning(f'Failed to extract totals from text: {text}')
    return None, None, None



async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    chat_id = update.message.chat_id
    message_id = update.message.message_id
    logger.info(f'Received message: {text}')

    # Check if the message contains the specific phrase
    if 'Summary of Tips and VIPs for' not in text:
        logger.warning('Message does not contain the specific phrase')
        return

    # Extract data from the message text
    name = extract_name(text)
    date = extract_date(text)
    shift = extract_shift(text)
    shift_hours = extract_shift_hours(text)
    creator = extract_creator(text)
    vip_tips = extract_vip_tips(text) or "$0"
    ppvs = extract_ppvs(text) or "$0"
    total_gross_sale, total_net_sale, total_bonus = extract_totals(text)

    # Generate the message link
    message_link = f"https://t.me/c/{chat_id}/{message_id}"

    # Set default value for total bonus if it's None
    total_bonus = total_bonus or "$0"

    # Log extracted data for debugging purposes
    logger.info(f'Extracted data: Name={name}, Date={date}, Shift={shift}, Shift Hours={shift_hours}, Creator={creator}, '
                f'VIP/Tips={vip_tips}, PPVs={ppvs}, Total Gross Sale={total_gross_sale}, '
                f'Total Net Sale={total_net_sale}, Total Bonus={total_bonus}, Message Link={message_link}')

    if not all([name, date, shift, shift_hours, total_gross_sale, total_net_sale, total_bonus]):
        logger.warning(f'Invalid input format: {text}')
        await update.message.reply_text('Hey! Please format your summary like this!\n👉🏻 https://t.me/c/1811961823/1719 👈🏻')
        return

    # Add message to the queue
    message_queue.append((update.message.chat_id, {
        'name': name,
        'date': date,
        'shift': shift,
        'shift_hours': shift_hours,
        'creator': creator,
        'vip_tips': vip_tips,
        'ppvs': ppvs,
        'total_gross_sale': total_gross_sale,
        'total_net_sale': total_net_sale,
        'total_bonus': total_bonus,
        'message_link': message_link
    }))

    # React with a check mark emoji
    try:
        await context.bot.set_message_reaction(chat_id, message_id, reaction="✍")
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
                data['name'],
                data['date'],
                data['shift'],
                data['shift_hours'],
                data['creator'],
                data['vip_tips'],
                data['ppvs'],
                data['total_gross_sale'],
                data['total_net_sale'],
                data['total_bonus'],
                data['message_link']
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
