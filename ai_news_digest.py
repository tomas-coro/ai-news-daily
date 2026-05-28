#!/usr/bin/env python3
"""AI News Daily — raccoglie news AI da feed RSS, le fa curare/tradurre da
Gemini (free tier) e invia un digest su Telegram, diviso per categorie.

Variabili d'ambiente richieste:
  TELEGRAM_BOT_TOKEN  token del bot Telegram
  TELEGRAM_CHAT_ID    chat_id del destinatario
  GEMINI_API_KEY      chiave Google AI Studio (free)
"""

import os
import sys
import json
import time
import html
import datetime as dt
from urllib import request, parse, error

import feedparser

# --- Config -----------------------------------------------------------------

GEMINI_MODEL = "gemini-2.0-flash"
LOOKBACK_HOURS = 48
MAX_ITEMS_TO_GEMINI = 60      # quante news grezze passiamo al modello
TELEGRAM_LIMIT = 4000        # margine sotto il limite reale di 4096

# Feed RSS gratuiti, raggruppati per "taglio" (Gemini ricategorizza comunque).
FEEDS = [
    # Annunci & modelli / news generali
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    # Lab / fonti ufficiali
    ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    # Ricerca / tool / community (proxy gratuiti di Twitter)
    ("Hacker News (AI)", "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+Claude&points=80"),
    ("r/LocalLLaMA", "https://www.reddit.com/r/LocalLLaMA/top/.rss?t=day"),
    ("r/MachineLearning", "https://www.reddit.com/r/MachineLearning/top/.rss?t=day"),
]


# --- Raccolta news ----------------------------------------------------------

def _entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return dt.datetime.fromtimestamp(time.mktime(t), tz=dt.timezone.utc)
    return None


def collect_items():
    cutoff = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=LOOKBACK_HOURS)
    items = []
    for source, url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] feed fallito {source}: {exc}", file=sys.stderr)
            continue
        for entry in feed.entries[:25]:
            when = _entry_time(entry)
            if when and when < cutoff:
                continue
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            summary = html.unescape((entry.get("summary") or "")).strip()
            # togli tag html grezzi dal summary
            if "<" in summary:
                import re
                summary = re.sub(r"<[^>]+>", " ", summary)
            summary = " ".join(summary.split())[:400]
            if not title or not link:
                continue
            items.append({
                "source": source,
                "title": title,
                "summary": summary,
                "link": link,
                "when": when.isoformat() if when else "",
            })
    # dedup per link
    seen, unique = set(), []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        unique.append(it)
    return unique[:MAX_ITEMS_TO_GEMINI]


# --- Gemini -----------------------------------------------------------------

def build_prompt(items, today_str):
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(
            f"{i}. [{it['source']}] {it['title']}\n"
            f"   {it['summary']}\n"
            f"   {it['link']}"
        )
    raw = "\n".join(lines) if lines else "(nessuna news trovata nei feed)"
    return f"""Sei l'editor di un digest quotidiano di news sull'intelligenza artificiale,\
 inviato su Telegram a un utente italiano appassionato di AI.

Qui sotto trovi le news grezze raccolte oggi ({today_str}) da vari feed.\
 Scegli le 10-15 PIU' rilevanti e interessanti, scarta doppioni e roba di poco conto,\
 e scrivi il messaggio finale per Telegram.

REGOLE DI FORMATO (testo semplice, NIENTE markdown, NIENTE asterischi):
- Inizia con: "☀️ AI News — {today_str}"
- Dividi in queste categorie (salta quelle vuote), con l'emoji e il titolo in maiuscolo:
  🚀 ANNUNCI & MODELLI
  🛠️ TOOL & USO PRATICO
  🔬 RICERCA & PAPER
  💬 DIBATTITO & COMMUNITY
  🎓 IMPARA (prompt, skill, consigli)
- Numera le voci progressivamente. Ogni voce su più righe:
  N. [EN] frase o titolo originale in inglese
     IT: sintesi chiara in italiano (1-2 frasi)
     🔗 link
- Gli URL vanno lasciati nudi (Telegram li rende cliccabili). Non accorciarli.
- Tono sintetico e concreto. Tutto il testo finale a parte la riga "[EN] ..." deve essere in italiano.
- Lunghezza totale: stai sotto i 3500 caratteri se possibile.

Se le news grezze sono poche o assenti, fai comunque del tuo meglio con quello che c'è\
 e aggiungi in fondo la riga "Giornata tranquilla sul fronte AI."

Rispondi SOLO con il testo del messaggio Telegram, nient'altro.

NEWS GREZZE:
{raw}
"""


def call_gemini(prompt, api_key):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["candidates"][0]["content"]["parts"][0]["text"].strip()


# --- Telegram ---------------------------------------------------------------

def split_message(text, limit=TELEGRAM_LIMIT):
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, data=data, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(f"Telegram error: {body}")
    return body


# --- Main -------------------------------------------------------------------

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    gemini_key = os.environ["GEMINI_API_KEY"]

    today_str = dt.datetime.now().strftime("%d/%m/%Y")

    items = collect_items()
    print(f"Raccolte {len(items)} news grezze dai feed.")

    try:
        message = call_gemini(build_prompt(items, today_str), gemini_key)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] Gemini fallito: {exc}", file=sys.stderr)
        message = (
            f"☀️ AI News — {today_str}\n\n"
            "Oggi non sono riuscito a generare il digest (problema temporaneo). "
            "Riprovo domani."
        )

    chunks = split_message(message)
    for i, chunk in enumerate(chunks, 1):
        send_telegram(token, chat_id, chunk)
        print(f"Inviato messaggio {i}/{len(chunks)} ({len(chunk)} caratteri).")
        time.sleep(1)

    print("Fatto.")


if __name__ == "__main__":
    main()
