# Promptuy autoposting. Commands: tick | add --file F [--window morning|evening|now] | set-text ID --file F
# | video-done ID --file F --check C | video-reject ID --check C | video-fail ID REASON | lesson TEXT | lessons | status | dm --file F | init
# | setup-commands. State = pinned JSON in the storage channel.
import html, json, os, random, re, sys, urllib.error, urllib.parse, urllib.request, uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

STORE = -1004350817622
CHANNEL = os.environ.get('PROMPTUY_CHANNEL', '@promptuy')
TZ = ZoneInfo('Europe/Warsaw')
REVIEW_MIN = 55
WINDOWS = {'morning': (8, 0, 11, 30), 'evening': (15, 0, 20, 30)}
TOKEN = os.environ['TG_BOT_TOKEN']
OWNER = str(os.environ['TG_CHAT_ID'])
NL = chr(10)
CRLF = chr(13) + chr(10)
FINAL = ('published', 'cancelled')
VIDEO_HOSTS = ('tiktok.com', 'youtube.com', 'youtu.be', 'instagram.com')
MAX_TRIES = 3
SLOT_DAY = (9, 0, 21, 30)
SLOT_GAP_MIN = (120, 180)
TICK_MINUTE = 17  # the publisher routine runs at HH:17


def api(method, files=None, **params):
    url = 'https://api.telegram.org/bot' + TOKEN + '/' + method
    if files:
        b = uuid.uuid4().hex
        body = b''
        for k, v in params.items():
            body += ('--' + b + CRLF + 'Content-Disposition: form-data; name=' + json.dumps(k) + CRLF + CRLF + str(v) + CRLF).encode()
        for k, (name, data) in files.items():
            head = '--' + b + CRLF + 'Content-Disposition: form-data; name=' + json.dumps(k) + '; filename=' + json.dumps(name)
            body += (head + CRLF + 'Content-Type: application/json' + CRLF + CRLF).encode() + data + CRLF.encode()
        body += ('--' + b + '--' + CRLF).encode()
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + b})
    else:
        data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items() if v is not None}
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b'{}')


def must(res, what):
    if not res.get('ok'):
        raise SystemExit('Telegram error in ' + what + ': ' + str(res.get('description')))
    return res['result']


def strip_tags(t):
    return html.unescape(re.sub('<[^>]+>', '', t))


def send_html(chat, text, **kw):
    res = api('sendMessage', chat_id=chat, text=text, parse_mode='HTML', **kw)
    if not res.get('ok') and 'parse' in (res.get('description') or '').lower():
        res = api('sendMessage', chat_id=chat, text=strip_tags(text), **kw)
    return must(res, 'sendMessage')


def now():
    v = os.environ.get('PROMPTUY_NOW')
    return datetime.fromisoformat(v).astimezone(timezone.utc) if v else datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds')


def parse(s):
    return datetime.fromisoformat(s)


def load():
    pin = must(api('getChat', chat_id=STORE), 'getChat').get('pinned_message') or {}
    if not pin.get('document'):
        raise SystemExit('No pinned state in storage channel.')
    path = must(api('getFile', file_id=pin['document']['file_id']), 'getFile')['file_path']
    with urllib.request.urlopen('https://api.telegram.org/file/bot' + TOKEN + '/' + path, timeout=40) as r:
        st = json.load(r)
    st['_pinned_id'] = pin['message_id']
    st.setdefault('requests', [])
    return st


def save(st):
    old = st.pop('_pinned_id', None)
    data = json.dumps(st, ensure_ascii=False, indent=1).encode()
    msg = must(api('sendDocument', files={'document': ('promptuy-state.json', data)}, chat_id=STORE,
                   disable_notification='true', caption='state ' + iso(now())), 'sendDocument')
    must(api('pinChatMessage', chat_id=STORE, message_id=msg['message_id'], disable_notification='true'), 'pin')
    if old:
        api('deleteMessage', chat_id=STORE, message_id=old)
    api('deleteMessage', chat_id=STORE, message_id=msg['message_id'] + 1)  # the pin service message
    st['_pinned_id'] = msg['message_id']


def pick_time(window):
    t = now()
    if window == 'now':
        return t
    local = t.astimezone(TZ)
    h1, m1, h2, m2 = WINDOWS[window]
    start = datetime(local.year, local.month, local.day, h1, m1, tzinfo=TZ)
    span = (h2 * 60 + m2) - (h1 * 60 + m1)
    if start + timedelta(minutes=span) < local:
        start += timedelta(days=1)
    return start + timedelta(minutes=random.randint(0, span))


def keyboard(pid):
    return {'inline_keyboard': [[
        {'text': '✅ Публікуй зараз', 'callback_data': 'ok:' + pid},
        {'text': '✏️ Редагувати', 'callback_data': 'ed:' + pid},
        {'text': '❌ Скасувати', 'callback_data': 'no:' + pid}]]}


def video_urls(txt):
    urls = re.findall('https?://[^ ' + NL + ']+', txt)
    return [u for u in urls if txt.startswith('/post') or any(h in u for h in VIDEO_HOSTS)]


def when(dt):
    tick_at = dt.replace(minute=TICK_MINUTE, second=0, microsecond=0)
    dt = tick_at if tick_at >= dt else tick_at + timedelta(hours=1)
    local, today = dt.astimezone(TZ), now().astimezone(TZ).date()
    day = {0: 'сьогодні', 1: 'завтра'}.get((local.date() - today).days, local.strftime('%d.%m'))
    return day + ' ~о ' + local.strftime('%H:%M')


def deadline_for(p, t):
    d = t + timedelta(minutes=REVIEW_MIN)
    if p.get('scheduled_at') and parse(p['scheduled_at']) > d:
        d = parse(p['scheduled_at'])
    return d


def next_slot(st):
    t = now()
    cand = t + timedelta(minutes=REVIEW_MIN)
    busy = [parse(p.get('scheduled_at') or p.get('publish_at') or p['notify_at']) for p in st['posts'] if p['status'] not in FINAL]
    later = [b for b in busy if b > t]
    if later:
        cand = max(cand, max(later) + timedelta(minutes=random.randint(*SLOT_GAP_MIN)))
    local = cand.astimezone(TZ)
    h1, m1, h2, m2 = SLOT_DAY
    start = local.replace(hour=h1, minute=m1, second=0, microsecond=0)
    if local < start:
        local = start + timedelta(minutes=random.randint(0, 40))
    elif local > local.replace(hour=h2, minute=m2, second=0, microsecond=0):
        local = start + timedelta(days=1, minutes=random.randint(0, 40))
    return local.astimezone(timezone.utc)


def find(st, pid):
    return next((p for p in st['posts'] if p['id'] == pid), None)


def reply_to(p):
    if p.get('preview_msg_id'):
        return {'message_id': p['preview_msg_id'], 'allow_sending_without_reply': True}
    return None


def mark_preview(p, note):
    if p.get('preview_msg_id'):
        api('editMessageReplyMarkup', chat_id=OWNER, message_id=p['preview_msg_id'], reply_markup={'inline_keyboard': []})
    send_html(OWNER, note, reply_parameters=reply_to(p))


def publish(p):
    res = api('sendMessage', chat_id=CHANNEL, text=p['text'], parse_mode='HTML')
    if not res.get('ok') and 'parse' in (res.get('description') or '').lower():
        res = api('sendMessage', chat_id=CHANNEL, text=strip_tags(p['text']))
    msg = must(res, 'publish')
    p.update(status='published', published_at=iso(now()), published_msg_id=msg['message_id'])
    link = 'https://t.me/' + CHANNEL.lstrip('@') + '/' + str(msg['message_id']) if CHANNEL.startswith('@') else ''
    mark_preview(p, ('✅ Опубліковано ' + link).strip())
    print('PUBLISHED', p['id'], link)


def tick(st):
    t = now()
    off = st.get('offset') or 0
    upd = must(api('getUpdates', offset=off + 1 if off else None, timeout=0,
                   allowed_updates=['message', 'callback_query']), 'getUpdates')
    for u in upd:
        st['offset'] = u['update_id']
        cq = u.get('callback_query')
        if cq and str(cq['from']['id']) == OWNER:
            api('answerCallbackQuery', callback_query_id=cq['id'], text='Прийняв, оброблю найближчим часом')
            action, _, pid = (cq.get('data') or '').partition(':')
            p = find(st, pid)
            if not p or p['status'] in FINAL:
                continue
            if action == 'ok':
                p['status'] = 'approved'
            elif action == 'no':
                p['status'] = 'cancelled'
                mark_preview(p, '❌ Скасовано, не публікую.')
            elif action == 'ed' and p['status'] == 'notified':
                p['status'] = 'edit_requested'
            continue
        m = u.get('message')
        txt = ((m or {}).get('text') or '').strip()
        if not m or str(m['chat']['id']) != OWNER or not txt:
            continue
        urls = video_urls(txt)
        if urls:
            for url in urls:
                st['requests'].append({'id': uuid.uuid4().hex[:6], 'url': url, 'status': 'pending', 'created': iso(t), 'tries': 0})
            n = len([r for r in st['requests'] if r['status'] == 'pending'])
            send_html(OWNER, '🎬 Прийняв, у черзі відео: ' + str(n) + '. Пости пришлю превʼю сюди і розкладу по годинах.')
        elif txt.startswith('/post'):
            send_html(OWNER, 'Надішли так: /post і посилання на TikTok, YouTube Shorts або Reels.')
        elif not txt.startswith('/'):
            waiting = [p for p in st['posts'] if p['status'] == 'feedback_asked']
            if waiting:
                waiting[-1].update(feedback=m['text'], status='rewrite_needed')
            else:
                st['lessons'].append({'date': iso(t)[:10], 'text': m['text'], 'source': 'owner'})
                send_html(OWNER, '📝 Записав як побажання для наступних постів.')
    for p in st['posts']:
        s = p['status']
        if s == 'approved':
            publish(p)
        elif s == 'queued' and parse(p['notify_at']) <= t:
            deadline = deadline_for(p, t)
            head = '📝 <b>Пост готовий.</b> Якщо нічого не натиснеш, опублікую ' + when(deadline) + '.'
            if p.get('source_url'):
                head += NL + '🎬 За відео: ' + html.escape(p['source_url'])
            if p.get('check'):
                head += NL + '🔎 <b>Перевірка:</b> ' + html.escape(p['check'])
            msg = send_html(OWNER, head + NL + NL + p['text'], reply_markup=keyboard(p['id']))
            p.update(status='notified', preview_msg_id=msg['message_id'], notified_at=iso(t), publish_at=iso(deadline))
            print('NOTIFIED', p['id'])
        elif s in ('notified', 'feedback_asked') and parse(p['publish_at']) <= t:
            publish(p)
        elif s == 'edit_requested':
            deadline = deadline_for(p, t)
            api('editMessageReplyMarkup', chat_id=OWNER, message_id=p['preview_msg_id'], reply_markup={'inline_keyboard': []})
            ask = ('✏️ <b>Що не так з постом?</b> Напиши одним повідомленням, я перепишу і врахую на майбутнє.' + NL +
                   'Якщо не відповіси, опублікую як є ' + when(deadline) + '.')
            send_html(OWNER, ask, reply_parameters=reply_to(p))
            p.update(status='feedback_asked', asked_at=iso(t), publish_at=iso(deadline))
            print('ASKED', p['id'])
        elif s == 'rewrite_needed':
            print(NL.join(['REWRITE ' + p['id'], '--- FEEDBACK ---', p['feedback'], '--- CURRENT TEXT ---', p['text'], '--- END ---']))
    for r in st['requests']:
        if r['status'] != 'pending':
            continue
        r['tries'] = r.get('tries', 0) + 1
        if r['tries'] > MAX_TRIES:
            fail_request(r, 'не вдалося за ' + str(MAX_TRIES) + ' спроби')
        else:
            print('VIDEO ' + r['id'] + ' ' + r['url'])
    cutoff = t - timedelta(days=30)
    st['posts'] = [p for p in st['posts'] if p['status'] not in FINAL or parse(p.get('published_at') or p['created']) > cutoff]
    st['requests'] = [r for r in st['requests'] if r['status'] == 'pending' or parse(r['created']) > cutoff]
    save(st)
    print('QUEUE', ' '.join(p['id'] + ':' + p['status'] for p in st['posts'] if p['status'] not in FINAL) or 'empty')


def fail_request(r, reason):
    r.update(status='failed', reason=reason)
    send_html(OWNER, '😕 Не вийшло зробити пост з відео ' + html.escape(r['url']) + NL + html.escape(reason))
    print('VIDEO FAILED', r['id'], reason)


def read_check(args):
    if '--check' not in args:
        raise SystemExit('--check FILE is required: fact-check verdict for the owner')
    txt = open(args[args.index('--check') + 1], encoding='utf-8').read().strip()
    if not txt:
        raise SystemExit('empty fact-check')
    return txt


def get_request(st, rid):
    r = next((r for r in st['requests'] if r['id'] == rid), None)
    if not r:
        raise SystemExit('no such video request')
    return r


def read_file(args):
    return open(args[args.index('--file') + 1], encoding='utf-8').read().strip()


def main():
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ('help', [])
    if cmd == 'init':
        backlog = must(api('getUpdates', timeout=0), 'getUpdates')
        save({'version': 2, 'offset': backlog[-1]['update_id'] if backlog else 0, 'posts': [], 'lessons': []})
        print('INIT ok')
        return
    if cmd == 'setup-commands':
        must(api('setMyCommands', commands=[{'command': 'post', 'description': 'Пост у Промптуй з TikTok / Shorts / Reels'}],
                 scope={'type': 'chat', 'chat_id': int(OWNER)}), 'setMyCommands')
        print('COMMANDS ok')
        return
    if cmd == 'dm':
        send_html(OWNER, read_file(args), link_preview_options={'is_disabled': True})
        print('DM sent')
        return
    st = load()
    if cmd == 'tick':
        tick(st)
    elif cmd == 'add':
        window = args[args.index('--window') + 1] if '--window' in args else (
            'morning' if now().astimezone(TZ).hour < 6 else 'evening')
        pid, at = uuid.uuid4().hex[:6], pick_time(window)
        st['posts'].append({'id': pid, 'text': read_file(args), 'status': 'queued', 'created': iso(now()),
                            'window': window, 'notify_at': iso(at)})
        save(st)
        print('ADDED', pid, 'preview at', at.astimezone(TZ).strftime('%Y-%m-%d %H:%M'), 'Warsaw')
    elif cmd == 'set-text':
        p = find(st, args[0])
        if not p:
            raise SystemExit('no such post')
        p['history'] = p.get('history', []) + [{'text': p['text'], 'feedback': p.get('feedback')}]
        p.update(text=read_file(args), status='queued', notify_at=iso(now()), feedback=None)
        save(st)
        print('UPDATED', p['id'], '- run tick to send the new preview')
    elif cmd == 'video-done':
        r = get_request(st, args[0])
        check = read_check(args)
        pid = uuid.uuid4().hex[:6]
        st['posts'].append({'id': pid, 'text': read_file(args), 'status': 'queued', 'created': iso(now()),
                            'window': 'video', 'notify_at': iso(now()), 'scheduled_at': iso(next_slot(st)),
                            'source_url': r['url'], 'check': check})
        r.update(status='done', post_id=pid, check=check)
        save(st)
        print('ADDED', pid, 'from video', r['id'], 'publish', when(parse(st['posts'][-1]['scheduled_at'])), '- run tick to send the preview')
    elif cmd == 'video-reject':
        r = get_request(st, args[0])
        check = read_check(args)
        r.update(status='rejected', check=check)
        send_html(OWNER, '🚫 <b>Не став робити пост:</b> відео не пройшло перевірку.' + NL + html.escape(r['url']) + NL + NL + html.escape(check))
        print('VIDEO REJECTED', r['id'])
        save(st)
    elif cmd == 'video-fail':
        fail_request(get_request(st, args[0]), ' '.join(args[1:]) or 'без пояснення')
        save(st)
    elif cmd == 'lesson':
        st['lessons'].append({'date': iso(now())[:10], 'text': ' '.join(args), 'source': 'agent'})
        save(st)
        print('LESSON saved')
    elif cmd == 'lessons':
        print(NL.join('- [' + l['date'] + '] ' + l['text'] for l in st['lessons']) or '(no lessons yet)')
    elif cmd == 'status':
        print('PENDING:')
        for p in st['posts']:
            if p['status'] not in FINAL:
                print(' ', p['id'], p['status'], p.get('notify_at'), strip_tags(p['text'])[:80])
        print('RECENT PUBLISHED/CANCELLED (do not repeat these topics):')
        for p in st['posts'][-20:]:
            if p['status'] in FINAL:
                print('  [' + p['status'] + ']', strip_tags(p['text'])[:120].replace(NL, ' '))
    else:
        print(open(__file__, encoding='utf-8').read().split(NL)[0])


if __name__ == '__main__':
    main()
