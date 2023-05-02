from dotenv import load_dotenv
import openai
import os
import time
from supabase import create_client
from threading import Thread
from farcaster import Warpcast
from farcaster.models import Parent
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
BOT_USERNAME = "artbotica"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)
wcc = Warpcast(os.environ.get("MNEMONIC"))
openai.api_key = os.environ.get("OPENAI_KEY")


def get_painting_info():
    result = supabase.table("paintings").select("*").eq("casted", False).limit(1).execute()
    if result.data:
        return result.data[0]
    return None


def get_gpt_response(painting_info):
    artist_name = painting_info["artist_name"]
    painting_name = painting_info["painting_name"]
    url = painting_info["url"]

    prompt1 = "You are an art bot which helps interpret an artist's painting. Describe the painting from the artist perspective."
    prompt2 = "Imagine a conversation between the artist (prefix with 🧑‍🎨) and a viewer (prefix with 🗣️) of their painting. Describe the artist's thoughts, feelings, and intentions when creating the piece. Consider their journey and the challenges faced while creating this painting, and how they overcame those challenges to create a powerful and unique work of art. Answer three questions as the artist."
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt1},
            {"role": "system", "content": prompt2},
            {"role": "user", "content": f"Artist: {artist_name}, Painting: {painting_name}"}
        ],
        max_tokens=750,
    )
    result = response.choices[0].message.content.strip()
    result = f"{url} {painting_name} by {artist_name}\n\n {result}"
    return result


def post_chunks(text, parent=None):
    # Break text into chunks of maximum 320 characters on complete sentences
    chunks = []
    start = 0
    end = 310
    while start < len(text):
        if end < len(text):
            while text[end] not in {'.', '!', '?', '"'} and end > start:
                end -= 1
            if end == start:
                end = start + 310
            else:
                end += 1
        else:
            end = len(text)
        chunks.append(text[start:end].strip())
        start = end
        end += 310

    # Post the first chunk as a thread response if parent is not None, otherwise post as a cast
    if parent:
        res = wcc.post_cast(text=chunks[0], parent=Parent(fid=parent.author.fid, hash=parent.hash))
    else:
        res = wcc.post_cast(text=chunks[0])

    # Post the remaining chunks as thread responses
    prev_res = res
    for chunk in chunks[1:]:
        prev_res = wcc.post_cast(text=chunk, parent=Parent(fid=prev_res.cast.author.fid, hash=prev_res.cast.hash))

    return prev_res



def update_casted_status(painting_info):
    supabase.table("paintings").update({"casted": True}).eq("id", painting_info["id"]).execute()


def run_daily_cast():
    while True:
        logging.info("Running daily cast")
        painting_info = get_painting_info()
        if painting_info:
            gpt_response = get_gpt_response(painting_info)
            if gpt_response:
                last_cast = post_chunks(gpt_response)
                update_casted_status(painting_info)
                logging.info(f"Posted art for {painting_info['painting_name']} by {painting_info['artist_name']}")
            else:
                logging.error("Failed to generate a response for the painting")
        else:
            logging.info("No art left to post")
        time.sleep(86400)


def get_gpt_response_for_question(original_cast_text, thread_cast_text):
    prompt = "You are an art bot who helps answer questions about paintings. Answer the following question as briefly as possible."

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "system", "content": thread_cast_text},
            {"role": "user", "content": f"{original_cast_text}"}
        ],
        max_tokens=300,
    )
    result = response.choices[0].message.content.strip()
    return result


def notification_stream():
    logging.info("Starting notification_stream loop")
    for notif in wcc.stream_notifications():
        try:
            if notif:
                thread_hash = notif.content.cast.thread_hash
                if thread_hash:
                    thread_cast = wcc.get_cast(thread_hash).cast
                    if thread_cast and thread_cast.author.username == BOT_USERNAME:
                        query_cast_text = notif.content.cast.text
                        thread_cast_text = thread_cast.text.split('\n')[0]
                        if query_cast_text.strip().endswith("?"):
                            likes = wcc.get_cast_likes(notif.content.cast.hash).likes
                            artbotica_liked = False
                            for like in likes:
                                if like.reactor.username == BOT_USERNAME:
                                    artbotica_liked = True
                                    break
                            if not artbotica_liked:
                                answer = get_gpt_response_for_question(query_cast_text, thread_cast_text)
                                post_chunks(answer, notif.content.cast)
                                wcc.like_cast(notif.content.cast.hash)
                                logging.info(f"Answered question: {query_cast_text}")
        except Exception as e:
            logging.info(f"Error in notification_stream: {e}")

if __name__ == "__main__":
    cron_thread = Thread(target=run_daily_cast)
    cron_thread.start()
    notification_stream()
