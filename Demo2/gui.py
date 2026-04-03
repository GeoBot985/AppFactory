import customtkinter as ctk
import threading
import asyncio
from assistant_core import WhatsAppAssistant, CHROME_DATA_DIR, PROFILE_NAME
from playwright.async_api import async_playwright

class App(ctk.CTk):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.assistant = None
        self.title("WhatsApp Stealth Assistant")
        self.geometry("600x480")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Controls Frame ---
        self.controls_frame = ctk.CTkFrame(self)
        self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.controls_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.controls_frame, text="Contact:").grid(row=0, column=0, padx=5, pady=5)
        self.contact_entry = ctk.CTkEntry(self.controls_frame, placeholder_text="Name or Group")
        self.contact_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.send_button = ctk.CTkButton(self.controls_frame, text="Send", command=self.send_message_callback, state="disabled")
        self.send_button.grid(row=0, column=2, padx=5, pady=5)

        ctk.CTkLabel(self.controls_frame, text="Message:").grid(row=1, column=0, padx=5, pady=5)
        self.message_entry = ctk.CTkEntry(self.controls_frame, placeholder_text="Type your message...")
        self.message_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(self.controls_frame, text="History:").grid(row=2, column=0, padx=5, pady=5)
        self.history_entry = ctk.CTkEntry(self.controls_frame, placeholder_text="Num messages")
        self.history_entry.insert(0, "10")
        self.history_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        self.history_button = ctk.CTkButton(self.controls_frame, text="Get History", command=self.get_history_callback, state="disabled")
        self.history_button.grid(row=2, column=2, padx=5, pady=5)


        # --- Log Box ---
        self.log_box = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.log_box.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # --- Status Bar ---
        self.status_label = ctk.CTkLabel(self, text="Status: Initializing...")
        self.status_label.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        # --- Start Assistant ---
        self.start_assistant_thread()

    def log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")
        with open("gui.log", "a", encoding="utf-8") as f:
            f.write(message + "\n")

    def set_status(self, message):
        self.status_label.configure(text=f"Status: {message}")

    def start_assistant_thread(self):
        self.set_status("Launching Playwright...")
        thread = threading.Thread(target=self.run_assistant_loop, daemon=True)
        thread.start()

    def run_assistant_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.initialize_assistant())
    
    async def initialize_assistant(self):
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=CHROME_DATA_DIR,
                channel="chrome",
                headless=False,
                args=[f"--profile-directory={PROFILE_NAME}"]
            )
            self.assistant = WhatsAppAssistant(context, self.log_callback)
            await self.assistant.startup()
            
            # Update UI from the main thread
            self.after(0, self.on_assistant_ready)
            
            # Start the message listener
            await self.assistant.listen_for_new_messages()
            
    def on_assistant_ready(self):
        self.set_status("Ready")
        self.send_button.configure(state="normal")
        self.history_button.configure(state="normal")
        self.log("Assistant is running. Monitoring for messages.")
        
    def log_callback(self, message):
        self.after(0, self.log, message)
        
    def send_message_callback(self):
        contact = self.contact_entry.get()
        message = self.message_entry.get()
        if not contact or not message:
            self.log("Error: Contact and message cannot be empty.")
            return
        
        self.log(f"Queueing send to: {contact}")
        asyncio.run_coroutine_threadsafe(self.assistant.send_reply(contact, message), self.loop)
        self.message_entry.delete(0, "end")

    def get_history_callback(self):
        contact = self.contact_entry.get()
        try:
            limit = int(self.history_entry.get())
        except ValueError:
            self.log("Error: Invalid number for history limit.")
            return

        if not contact:
            self.log("Error: Contact cannot be empty.")
            return
            
        self.log(f"Queueing history fetch for: {contact}")
        future = asyncio.run_coroutine_threadsafe(self.assistant.get_history(contact, limit), self.loop)
        future.add_done_callback(self.on_history_done)

    def on_history_done(self, future):
        try:
            history = future.result()
            if history:
                self.log_callback(f"--- History for {self.contact_entry.get()} ---")
                for msg in history:
                    self.log_callback(f"- {msg}")
                self.log_callback("--- End of History ---")
            else:
                self.log_callback(f"No history found for {self.contact_entry.get()}.")
        except Exception as e:
            self.log_callback(f"Error fetching history: {e}")


def main():
    loop = asyncio.new_event_loop()
    app = App(loop)
    app.mainloop()

if __name__ == "__main__":
    main()
