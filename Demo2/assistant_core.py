import asyncio
import random
import hashlib
import re
import duckdb
from playwright.async_api import async_playwright
import os

# --- CONFIGURATION ---
CHROME_DATA_DIR = os.path.join(os.path.expanduser('~'), ".gemini", "tmp", "chrome_data")
PROFILE_NAME = "Default"  # Change to "Profile 1", etc. if needed
DB_PATH = "whatsapp_memory.duckdb"

class MessageTracker:
    def __init__(self):
        self.db = duckdb.connect(DB_PATH)
        self.db.execute("CREATE TABLE IF NOT EXISTS msgs (hash TEXT PRIMARY KEY, ts TIMESTAMP)")

    def is_new(self, sender, text):
        msg_hash = hashlib.sha256(f"{sender}{text}".encode()).hexdigest()
        exists = self.db.execute("SELECT 1 FROM msgs WHERE hash=?", [msg_hash]).fetchone()
        if not exists:
            self.db.execute("INSERT INTO msgs VALUES (?, CURRENT_TIMESTAMP)", [msg_hash])
            return True
        return False

class WhatsAppAssistant:
    def __init__(self, context, log_callback):
        self.context = context
        self.page = None
        self.tracker = MessageTracker()
        self.log = log_callback

    async def stealth_delay(self, min_s=1.5, max_s=4.0):
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def startup(self):
        self.page = await self.context.new_page()
        await self.page.goto("https://web.whatsapp.com")
        self.log("Waiting for WhatsApp to load...")
        # Wait for the chat list to appear
        await self.page.wait_for_selector("div[aria-label='Chat list']", timeout=60000)
        self.log("WhatsApp loaded successfully.")

    # --- THE OBSERVER (Event-Driven) ---
    async def listen_for_new_messages(self):
        self.log("Observer active: Monitoring for new messages...")
        chat_list_selector = "div[aria-label='Chat list'] > div"
        while True:
            await self.stealth_delay(3, 7)
            try:
                # 1. Focus on the top-most chat
                top_chat = await self.page.query_selector(chat_list_selector)
                if not top_chat:
                    continue

                # 2. Check for an unread badge (most reliable)
                unread_badge = await top_chat.query_selector("span[aria-label*='unread message']")
                
                # 3. As a fallback, check for a new timestamp (e.g., "11:24") vs a date ("Yesterday")
                is_new_time = False
                time_selector = "div[aria-label] > div:nth-child(2) > div:nth-child(2) span"
                time_el = await top_chat.query_selector(time_selector)
                if time_el:
                    time_text = await time_el.inner_text()
                    # Simple regex to check for format like HH:MM
                    if re.match(r'^\d{1,2}:\d{2}$', time_text):
                        is_new_time = True

                if unread_badge or is_new_time:
                    # 4. Extract sender and message snippet
                    sender_el = await top_chat.query_selector("div[aria-label] > div:nth-child(2) > div:nth-child(1) span[title]")
                    message_el = await top_chat.query_selector("div[aria-label] > div:nth-child(2) > div:nth-child(2) span[title]")
                    
                    if sender_el and message_el:
                        sender = await sender_el.get_attribute('title')
                        text = await message_el.get_attribute('title')
                        
                        # 5. Use tracker to see if we've processed this already
                        if self.tracker.is_new(sender, text):
                            self.log(f"EVENT: New message from {sender}: \"{text}\"")

            except Exception as e:
                self.log(f"Error in listener: {e}")


    # --- THE ARCHIVIST (Explicit Request) ---
    async def get_history(self, contact_name, limit=10):
        self.log(f"Archivist: Fetching last {limit} messages for {contact_name}")
        try:
            # 1. Use the search bar to find the contact
            search_input_selector = 'input[aria-label="Search input"]'
            await self.page.wait_for_selector(search_input_selector, timeout=60000)
            await self.page.fill(search_input_selector, contact_name)
            await self.stealth_delay()

            # 2. Click the corresponding chat in the results
            chat_selector = f"div[aria-label='Chat list'] span[title='{contact_name}']"
            await self.page.click(chat_selector)
            await self.stealth_delay()

            # 3. Scrape the text from the last N message bubbles
            # Using a more stable selector that finds the message content container
            messages_selector = "div.message-in, div.message-out"
            await self.page.wait_for_selector(messages_selector, timeout=5000)
            
            # Query all message containers
            message_elements = await self.page.query_selector_all(messages_selector)

            history = []
            # Slice to get the last 'limit' messages
            for msg_el in message_elements[-limit:]:
                # The actual text is in a span with this class
                text_el = await msg_el.query_selector("span.selectable-text")
                if text_el:
                    history.append(await text_el.inner_text())
            
            self.log(f"Found {len(history)} messages for {contact_name}.")
            return history

        except Exception as e:
            self.log(f"Error getting history for {contact_name}: {e}")
            await self.page.screenshot(path='get_history_error.png')
            return []

    async def send_reply(self, contact_name, text):
        self.log(f"Action: Sending reply to {contact_name}")
        try:
            # 1. Find and open the chat (leverages get_history's search logic)
            search_input_selector = 'input[aria-label="Search input"]'
            await self.page.wait_for_selector(search_input_selector, timeout=60000)
            await self.page.fill(search_input_selector, contact_name)
            await self.stealth_delay()

            chat_selector = f"div[aria-label='Chat list'] span[title='{contact_name}']"
            await self.page.click(chat_selector)
            await self.stealth_delay()
            
            # 2. Find the message input box and click it
            compose_box_selector = "div[data-testid='conversation-compose-box-input']"
            await self.page.click(compose_box_selector)
            
            # 3. Type with human-like jitter
            for char in text:
                await self.page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.05, 0.15)) # 50-150ms delay
            
            # 4. Send the message
            await self.page.keyboard.press('Enter')
            self.log("Message sent.")
            
            # 5. Clear the search bar for the next operation
            await self.page.fill(search_input_selector, "")

        except Exception as e:
            self.log(f"Error sending reply to {contact_name}: {e}")
            await self.page.screenshot(path='send_reply_error.png')