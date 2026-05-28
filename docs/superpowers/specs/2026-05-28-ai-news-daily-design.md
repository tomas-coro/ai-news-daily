# AI News Daily — Design

**Data:** 2026-05-28
**Stato:** approvato dall'utente, pronto per il piano di implementazione

## Obiettivo

Ricevere ogni mattina su **Telegram** un digest delle news AI "da Twitter/X",
in **lingua originale (inglese) + traduzione/sintesi in italiano**, organizzato
per categorie. Lettura comoda da telefono.

## Decisioni chiave (dal brainstorming)

| Tema | Decisione |
|------|-----------|
| Canale di consegna | **Telegram** (bot → chat, con notifica push) |
| Fonte news | **Ricerca web mirata** (gratis). Twitter API ufficiale esclusa (costo ~200$/mese, scraping fragile) |
| Contenuto | Tutte le categorie + sezione "Impara" (prompt, skill, consigli) |
| Organizzazione | **Diviso per categorie** |
| Lunghezza | **Medio: ~10-15 news** |
| Orario | **08:00 ora italiana**, ogni giorno |
| Esecuzione | **Routine schedulata di Claude Code** (agente in cloud) |
| Lingua | Originale (EN) + traduzione italiana fatta dall'agente |

## Architettura

Una **routine schedulata di Claude Code** (cron `0 8 * * *`, timezone Europe/Rome)
che lancia un agente Claude con un prompt fisso. Nessun server o script da
mantenere: l'agente *è* il programma. Gira in cloud, quindi funziona anche a PC
spento.

## Flusso giornaliero

1. **Ricerca** — più ricerche web mirate sulle news AI delle ultime ~24h, una
   per categoria.
2. **Selezione** — sceglie le 10-15 news migliori, scarta doppioni e roba
   vecchia, conserva il link fonte.
3. **Sintesi + traduzione** — per ogni news: frase chiave in originale (EN) +
   sintesi/traduzione in italiano + link.
4. **Formattazione** — messaggio diviso per categorie con emoji.
5. **Invio** — POST all'API Telegram (`sendMessage`) verso il bot dell'utente.

## Categorie del digest

- 🚀 **Annunci & modelli** — nuovi modelli, release, feature
- 🛠️ **Tool & uso pratico** — strumenti AI nuovi, trucchi, applicazioni concrete
- 🔬 **Ricerca & paper** — novità dalla ricerca, paper, thread tecnici
- 💬 **Dibattito** — discussioni, hot take, trend della community
- 🎓 **Impara** — prompt interessanti, skill nuove, consigli pratici per imparare

## Formato messaggio Telegram

```
☀️ AI News — 28 maggio 2026

🚀 ANNUNCI & MODELLI
1. [EN] "OpenAI ships GPT-X with…"
   🇮🇹 OpenAI rilascia GPT-X con… 🔗 link

🛠️ TOOL & USO PRATICO
2. …

… (altre categorie) …

🎓 IMPARA (prompt, skill, consigli)
N. …
```

Se supera il limite di lunghezza di un messaggio Telegram (~4096 caratteri),
viene spezzato automaticamente in più messaggi.

## Prerequisiti (setup una tantum, lato utente — con guida)

1. **Token bot Telegram** ottenuto da `@BotFather`.
2. **`chat_id`** dell'utente (ricavato con procedura guidata).
3. I due valori vengono inseriti nelle istruzioni della routine.

## Gestione errori / casi limite

- **Poche news nel giorno** → manda quelle che trova + riga "giornata tranquilla".
- **Ricerca fallita** → riprova; se nulla, manda breve avviso invece di restare muto.
- **Solo contenuti in inglese** → normale; l'italiano è la traduzione dell'agente.

## Fuori scope (YAGNI, per ora)

- Database storico delle news
- Filtri personalizzati avanzati
- Immagini / anteprime link
- Account Twitter specifici via API a pagamento (rivedibile in futuro)

## Possibili evoluzioni future

- Aggiungere fonti via servizio scraping Twitter a pagamento se serve più fedeltà.
- Comandi al bot (es. "/oggi" on-demand, scelta categorie).
- Archivio web (PWA) dei digest passati.
