import logging
import gspread
import re
import asyncio
from collections import deque
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("tasty-service-acct-creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key("sheet").sheet1

# Queue to hold incoming messages
message_queue = deque()

# Extraction functions
def extract_name(text):
    match = re.search(r'Summary of Tips and VIPs for\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_date_shift(text):
    match = re.search(r'(\w+ \d+, \d+:\s*\d+AM-\d+AM PST)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_creator(text):
    match = re.search(r'Creator :\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_vip_tips(text):
    matches = re.findall(r'\$(\d+) TIP from @\w+', text, re.IGNORECASE)
    if matches:
        return ', '.join(matches)
    return None

def extract_ppvs(text):
    matches = re.findall(r'\$(\d+) PPV PAID (from )?@\w+', text, re.IGNORECASE)
    if matches:
        return ', '.join(match[0] for match in matches)
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

# Define a few command handlers
async def start(update: Update, context: CallbackContext) -> None:
    logger.info('Received /start command')
    await update.message.reply_text('Hi! I am your bot.')

async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    logger.info(f'Received message: {text}')
    
    # Add message to the queue
    message_queue.append(text)

async def process_queue(context: CallbackContext) -> None:
    if message_queue:
        batch = list(message_queue)
        message_queue.clear()
        
        # Process each message in the batch
        for text in batch:
            name = extract_name(text)
            date_shift = extract_date_shift(text)
            creator = extract_creator(text)
            vip_tips = extract_vip_tips(text)
            ppvs = extract_ppvs(text)
            total_gross_sale = extract_total_gross_sale(text)
            total_net_sale = extract_total_net_sale(text)
            
            # Log extracted data
            logger.info(f'Extracted data: name={name}, date_shift={date_shift}, creator={creator}, vip_tips={vip_tips}, ppvs={ppvs}, total_gross_sale={total_gross_sale}, total_net_sale={total_net_sale}')
            
            # Append a new row to the Google Sheet with the extracted data
            try:
                row = [name, date_shift, 'Shift (8 hours)', creator, vip_tips, ppvs, total_gross_sale, total_net_sale, total_net_sale]
                await asyncio.to_thread(sheet.append_row, row)
                logger.info('Data appended to Google Sheet')
            except Exception as e:
                logger.error(f'Error appending data to Google Sheet: {e}')

def main() -> None:
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("TG BOT KEY").build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))

    # on non-command i.e message - handle the message
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the queue processing task
    job_queue = application.job_queue
    job = job_queue.run_repeating(process_queue, interval=30, first=0)
    job.modify(max_instances=3)  # Set the maximum number of concurrent instances

    # Start the Bot
    logger.info('Starting the bot...')
    application.run_polling()

if __name__ == '__main__':
    main()
