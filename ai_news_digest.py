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

GEMINI_MODEL = "gemini-2.5-flash"
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


# Categorie del digest: (chiave usata da Gemini, emoji, etichetta).
CATEGORIES = [
    ("annunci", "🚀", "Annunci & modelli"),
    ("tool", "🛠️", "Tool & uso pratico"),
    ("ricerca", "🔬", "Ricerca & paper"),
    ("dibattito", "💬", "Dibattito & community"),
    ("impara", "🎓", "Impara"),
]
CATEGORY_KEYS = [c[0] for c in CATEGORIES]


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
 inviato su Telegram a un utente italiano appassionato di AI ({today_str}).

Qui sotto trovi le news grezze raccolte dai feed. Scegli le 10-15 PIU' rilevanti\
 e interessanti, scarta doppioni e roba di poco conto.

Rispondi SOLO con un oggetto JSON valido in questa forma:
{{"items": [
  {{"cat": "<categoria>", "en": "<titolo/frase originale in INGLESE>",
    "it": "<sintesi chiara in ITALIANO, 1-2 frasi>", "url": "<link della fonte>"}}
]}}

Regole:
- "cat" DEVE essere una di: {", ".join(CATEGORY_KEYS)}
  (annunci=nuovi modelli/release/feature; tool=strumenti e usi pratici;
   ricerca=paper e novità di ricerca; dibattito=discussioni/opinioni/trend della community;
   impara=prompt utili, skill nuove, consigli pratici per imparare).
- "url" deve essere il link esatto preso dalla news grezza corrispondente.
- "en" resta in inglese (originale); "it" è la tua sintesi in italiano.
- 10-15 voci totali, ordinate per importanza. Niente testo fuori dal JSON.

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
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
            # gemini-2.5-flash usa il "thinking" che consuma il budget di output:
            # lo azzeriamo per avere la risposta completa.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    data = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(4):
        try:
            req = request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
            return parse_gemini_json(text)
        except error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 500, 503) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise last_err


def parse_gemini_json(text):
    # togli eventuali recinti ```json ... ```
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    data = json.loads(text)
    items = data.get("items", []) if isinstance(data, dict) else []
    cleaned = []
    for it in items:
        cat = (it.get("cat") or "").strip().lower()
        if cat not in CATEGORY_KEYS:
            cat = "annunci"
        en = (it.get("en") or "").strip()
        itx = (it.get("it") or "").strip()
        url = (it.get("url") or "").strip()
        if en and itx:
            cleaned.append({"cat": cat, "en": en, "it": itx, "url": url})
    return cleaned


# --- Rendering messaggio (HTML Telegram) ------------------------------------

def esc(text):
    """Escape per HTML parse_mode di Telegram."""
    return html.escape(text, quote=True)


def render_blocks(items, today_str):
    """Ritorna (header, [blocco_categoria, ...]) in HTML Telegram."""
    header = (
        "<pre>$ ai-news --today\n"
        f"✓ {esc(today_str)}</pre>"
    )
    blocks = []
    for key, emoji, label in CATEGORIES:
        cat_items = [it for it in items if it["cat"] == key]
        if not cat_items:
            continue
        head = f"<b>{emoji} {esc(label)} ({len(cat_items)})</b>"
        rows = []
        for it in cat_items:
            url = it["url"]
            en = esc(it["en"])
            # il titolo stesso è il link: si tocca per aprire/salvare l'articolo
            title = f'<a href="{esc(url)}"><b>{en}</b></a>' if url else f"<b>{en}</b>"
            rows.append(f"{title}\n<i>{esc(it['it'])}</i>")
        body = "\n\n".join(rows)
        blocks.append(f"<blockquote expandable>{head}\n\n{body}</blockquote>")
    return header, blocks


def pack_messages(header, blocks, limit=TELEGRAM_LIMIT):
    """Raggruppa header + blocchi-categoria in messaggi sotto il limite,
    senza mai spezzare un blocco (l'HTML resterebbe rotto)."""
    if not blocks:
        return [header + "\n\nGiornata tranquilla sul fronte AI."]
    messages, current = [], header
    for block in blocks:
        candidate = current + "\n\n" + block
        if len(candidate) > limit and current != header:
            messages.append(current)
            current = block
        else:
            current = candidate
        # se un singolo blocco supera il limite, lo manda comunque da solo
        if len(current) > limit and current == block:
            messages.append(current)
            current = ""
    if current:
        messages.append(current)
    return messages


# --- Telegram ---------------------------------------------------------------

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
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
        news = call_gemini(build_prompt(items, today_str), gemini_key)
        print(f"Gemini ha selezionato {len(news)} notizie.")
        header, blocks = render_blocks(news, today_str)
        messages = pack_messages(header, blocks)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] generazione fallita: {exc}", file=sys.stderr)
        messages = [
            "<pre>$ ai-news --today\n✗ errore</pre>\n\n"
            "Oggi non sono riuscito a generare il digest (problema temporaneo). "
            "Riprovo domani."
        ]

    for i, msg in enumerate(messages, 1):
        send_telegram(token, chat_id, msg)
        print(f"Inviato messaggio {i}/{len(messages)} ({len(msg)} caratteri).")
        time.sleep(1)

    print("Fatto.")


if __name__ == "__main__":
    main()
