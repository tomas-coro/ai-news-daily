# AI News Daily

Agente che ogni mattina alle **08:00 (ora italiana)** manda su **Telegram** un
digest delle news AI delle ultime 24-48h, diviso per categorie, con frase in
inglese (originale) + sintesi in italiano + link.

## Come funziona

È una **routine schedulata di Claude Code** (agente remoto in cloud). Non c'è
codice da eseguire localmente: l'agente *è* il programma. Ogni giorno fa
ricerche web, seleziona le notizie, le traduce e le invia al bot Telegram.

## Componenti

| Componente | Valore |
|------------|--------|
| Bot Telegram | `@AiNius_bot` (nome: *Ai News Daily*) |
| chat_id destinatario | `144574389` |
| Routine ID | `trig_01XGZCqMRhg5UjZZgqMbR9vf` |
| Schedule | `0 6 * * *` UTC = 08:00 Europe/Rome (ora legale) |
| Modello | `claude-sonnet-4-6` |
| Ambiente | `env_01LqG4QzRKiJ7D9dkQGbmaRr` (Default) |

## Gestione

- Pannello routine: https://claude.ai/code/routines/trig_01XGZCqMRhg5UjZZgqMbR9vf
- Tutte le routine: https://claude.ai/code/routines

## Note

- **Ora legale/solare:** il cron è in UTC fisso. `0 6 * * *` = 08:00 in ora
  legale (CEST, UTC+2, ~mar-ott). In ora solare (CET, UTC+1) diventerebbe 07:00:
  per riavere le 08:00 in inverno, aggiornare il cron a `0 7 * * *`.
- **Token Telegram:** è dentro le istruzioni della routine. Se viene
  rigenerato da BotFather, aggiornare la routine (azione `update`).
- La spec di design è in `docs/superpowers/specs/`.

## Possibili evoluzioni

- Comando `/oggi` on-demand al bot.
- Archivio web (PWA) dei digest.
- Fonti Twitter via API a pagamento per più fedeltà.
