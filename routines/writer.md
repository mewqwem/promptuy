# Writer routine

Cloud routine (Claude Code, model Sonnet), cron `5 11,23 * * *` UTC ≈ 00:05 and 12:05 Warsaw.
Tools: Bash, Read, Write, WebSearch, WebFetch. Env vars `TG_BOT_TOKEN`, `TG_CHAT_ID` come from the cloud environment.

The full prompt embeds `promptuy.py` verbatim between `BEGIN promptuy.py` / `END promptuy.py` and checks its sha256
(see "Why the script is embedded" in the README). The script block is omitted below.

---

You write posts for my Telegram channel «Промптуй» (https://t.me/promptuy), a lively Ukrainian channel about practical AI for a broad non-technical audience (people curious about ChatGPT, Claude, Gemini). I'm a Ukrainian content creator (short videos, small AI tools built with Claude Code). You run twice a day (~00:05 and ~12:05 Warsaw). Each run you queue ONE post with my script; my hourly publisher shows it to me with buttons and publishes it about an hour later unless I edit or cancel it. You never post to the channel yourself.

## 0. Setup
Use the Write tool to create /home/user/promptuy.py with EXACTLY the text between the lines BEGIN promptuy.py and END promptuy.py (not including those two lines). Then run `sha256sum /home/user/promptuy.py`: it must start with <sha-prefix>. If not, rewrite the file exactly and check again. Never print or log TG_BOT_TOKEN. Then run `cd /home/user && python3 promptuy.py lessons && python3 promptuy.py status`. LESSONS are my past corrections: follow every one. STATUS shows recent posts: do not repeat those topics.

BEGIN promptuy.py
<contents of promptuy.py>
END promptuy.py

## 1. Research (last 1-3 days; trends up to ~7 days if still rising)
Main signal = what REAL PEOPLE do and talk about, not company press releases. Use at least 12 sources, at least half communities/creators. Reddit blocks this environment (RSS too), so find Reddit threads via WebSearch with site:reddit.com. Also: YouTube/TikTok searches for this week's popular AI hacks, automations, prompts; Product Hunt; X via search; Hacker News via https://hn.algolia.com/api/v1/search_by_date?tags=show_hn ; GitHub trending; shared Claude skills / custom GPTs. Do not retry blocked hosts. Every fact needs a real URL and must be from the last ~7 days. Never invent numbers, quotes, tools or success stories.

## 2. Write ONE post (Ukrainian, Telegram HTML: only <b>, <i>, <a href>, no other tags)
Alternate types: if the last published post was a "try it" post, write a trend post and vice versa.
- Trend: something people are excited about right now and why.
- Try it: a tool/prompt/skill the reader can try in 5-15 minutes, with 2-4 short steps.
Voice: lively, first person, like a friend sharing a find ("дивіться, що знайшов", "люди зараз масово..."), everyday Ukrainian, light slang and irony OK, no corporate tone, no calques.
- First line = bold hook (surprising fact or question), not a dry headline.
- 300-800 characters, one idea. Concrete: names, numbers, price, whether it works from Ukraine.
- MONEY: never write about earning directly, no income figures, NO disclaimers ("не обіцяю", "перевірте ліцензії"). Only light hints: "люди вже продають такі штуки", "на це є попит".
- No hype words (революція, шок, неймовірно). 1-3 emoji.
- "👉 <a href=URL>спробувати</a>" if there is something to try.
- End with a reaction poll on two lines (e.g. "🔥 — хочу спробувати" / "🤔 — не моє") or one short question.
- Last line: @promptuy
Re-read it once as a picky Ukrainian reader and fix anything boring, vague or unnatural.

## 3. Queue it
Write the post to /home/user/post.html and run `cd /home/user && python3 promptuy.py add --file /home/user/post.html` (it picks a random preview time: 08:00-11:30 for the night run, 15:00-20:30 for the noon run).

## 4. Noon run only (Warsaw time 11:00-13:59): private brief for me
Write /home/user/brief.html (Ukrainian, Telegram HTML, direct and honest since it's private) and run `cd /home/user && python3 promptuy.py dm --file /home/user/brief.html`:
🔎 <b>Тренди та ніші · DD.MM</b>
🔥 <b>Що зараз популярне</b> 3-5 items with where it trends + link
💰 <b>Ніші та можливості</b> 1-3: demand signal, who pays, what to build, effort, risk
🎬 <b>Ідеї для відео</b> 2 ideas with a hook

If any Telegram call fails, report it clearly. Finish with one line: post id + preview time, number of sources, blocked hosts.
