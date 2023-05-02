import os
import time
from dotenv import load_dotenv
from farcaster import Warpcast
from threading import Thread

load_dotenv()

BOT_USERNAME = "artbotica"

# Define a function to run the cron job
def print_hello_world():
    while True:
        print("hello world")
        time.sleep(60)

# Define a function to run the notification stream
def notification_stream(fcc):
    for notif in fcc.stream_notifications():
        if notif:
            thread_hash = notif.content.cast.thread_hash
            if thread_hash:
                thread_cast = fcc.get_cast(thread_hash).cast
                print(thread_cast)
                if thread_cast and thread_cast.author.username == BOT_USERNAME:
                    context = {
                        "original_cast_text": notif.content.cast.text,
                        "thread_cast_text": thread_cast.text
                    }
                    print(context)
                    # Send the context to GPT
                    # Your GPT request code here
                    print("reply in thread")

if __name__ == "__main__":
    wcc = Warpcast(os.environ.get("MNEMONIC"))

    # Start the cron job in a separate thread
    cron_thread = Thread(target=print_hello_world)
    cron_thread.start()

    # Start the notification stream in the main thread
    notification_stream(wcc)
