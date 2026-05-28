# AI News Daily

Bot che ogni mattina alle **08:00 (ora italiana)** manda su **Telegram** un
digest delle news AI delle ultime 24-48h, diviso per categorie, con frase in
inglese (originale) + sintesi in italiano + link.

## Come funziona

Un **GitHub Actions** schedulato (cron) gira ogni giorno:
1. raccoglie news AI da vari feed RSS (`ai_news_digest.py`),
2. le fa selezionare, categorizzare e tradurre in italiano da **Google Gemini**
   (piano gratuito),
3. invia il digest al bot **Telegram**.

Gira nei server di GitHub: nessun PC acceso, costo zero.

## Componenti

| Componente | Valore |
|------------|--------|
| Bot Telegram | `@AiNius_bot` (nome: *Ai News Daily*) |
| Script | `ai_news_digest.py` |
| Workflow | `.github/workflows/daily.yml` (cron `0 6 * * *` UTC = 08:00 CEST) |
| Modello AI | `gemini-2.5-flash` (free tier, thinking disabilitato) |

## Segreti richiesti (GitHub → Settings → Secrets and variables → Actions)

| Nome segreto | Cosa contiene |
|--------------|---------------|
| `TELEGRAM_BOT_TOKEN` | token del bot (da @BotFather) |
| `TELEGRAM_CHAT_ID` | id chat destinatario |
| `GEMINI_API_KEY` | chiave Google AI Studio (free) |

## Test manuale

GitHub → tab **Actions** → workflow *AI News Daily* → **Run workflow**.

## Note

- **Ora legale/solare:** il cron è in UTC fisso. `0 6 * * *` = 08:00 in ora
  legale (CEST). In ora solare (inverno) diventa 07:00: per riavere le 08:00
  cambiare il cron a `0 7 * * *`.
- I feed RSS sono in `FEEDS` dentro `ai_news_digest.py`: aggiungere/togliere
  fonti lì.
- Storia: il primo tentativo usava una routine schedulata di Claude Code, ma
  quell'ambiente non può contattare Telegram (rete isolata). Da qui il passaggio
  a GitHub Actions. Vedi `docs/superpowers/specs/`.

## Possibili evoluzioni

- Comando `/oggi` on-demand al bot.
- Archivio web (PWA) dei digest.
- Fonti Twitter via API a pagamento per più fedeltà.
