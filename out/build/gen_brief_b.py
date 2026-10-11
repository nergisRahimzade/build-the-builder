"""Generate out/brief-b.workflow.json for Brief B (Brief A plus up to three products)."""
import json, pathlib

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
OUT = pathlib.Path(__file__).resolve().parent.parent / "brief-b.workflow.json"
MAXP = 3

# ---------------------------------------------------------------- python snippets (no double braces allowed)
DATE_HELPERS = r'''
import datetime, re, json
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def say(d):
    return DN[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1] + ' ' + str(d.year)
def sayiso(d):
    return say(d) + ' [' + d.isoformat() + ']'
def nextbd(d):
    d = d + ONE
    while not isbd(d):
        d = d + ONE
    return d
def parse_now():
    raw = str(vars.get('now') or '')
    m = re.match(r'\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2}))?', raw)
    t = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return t, int(m.group(4) or 0), int(m.group(5) or 0)
'''

SETUP_CODE = DATE_HELPERS + r'''
try:
    today, hh, mi = parse_now()
    nowt = '%02d:%02d' % (hh, mi)
    nb = nextbd(today)
    lines = ['Current date and time: ' + say(today) + ', ' + nowt + ' [' + today.isoformat() + '].']
    if hh * 60 + mi < 19 * 60:
        lines.append('Callback TODAY is possible: date ' + today.isoformat() + ', a time later than ' + nowt + ' and between 10:00 and 19:00 (both included).')
    else:
        lines.append('A callback today is NOT possible any more (it is after 19:00).')
    lines.append('Callback on the NEXT BUSINESS DAY is possible: ' + sayiso(nb) + ', a time between 10:00 and 19:00 (both included).')
    lines.append('Any other day (for example ' + say(nextbd(nb)) + ' or a weekend) or any time before 10:00 or after 19:00 is OUTSIDE the window.')
    vars['callback_facts'] = '\n'.join(lines)
    vars['setup_state'] = 'ok'
except Exception:
    vars['callback_facts'] = 'Current date and time: ' + str(vars.get('now')) + '. A callback is possible today or on the next business day (Monday to Friday, not a bank holiday), between 10:00 and 19:00, later than now.'
    vars['setup_state'] = 'fallback'
'''

ACCOUNT_CODE = DATE_HELPERS + r'''
def get_products():
    cands = []
    for k in ('products', 'fetch_account_response.data.products', 'get_account_response.data.products'):
        if k in vars:
            cands.append(vars.get(k))
    for v in cands:
        if isinstance(v, str):
            s = v.strip()
            try:
                v = json.loads(s)
            except Exception:
                try:
                    import ast
                    v = ast.literal_eval(s)
                except Exception:
                    v = None
        if isinstance(v, dict):
            v = [v]
        if isinstance(v, list):
            rows = [x for x in v if isinstance(x, dict)]
            if rows:
                return rows
    rows = dict()
    for k in list(vars.keys()):
        m = re.search(r'products\.(\d+)\.([A-Za-z0-9_]+)$', str(k))
        if m:
            i = int(m.group(1))
            if i not in rows:
                rows[i] = dict()
            rows[i][m.group(2)] = vars.get(k)
    return [rows[i] for i in sorted(rows)]
def money(x):
    x = round(float(x), 2)
    if abs(x - round(x)) < 0.005:
        return format(int(round(x)), ',')
    return format(x, ',.2f')
def num(x):
    x = round(float(x), 2)
    return str(int(round(x))) if abs(x - round(x)) < 0.005 else ('%.2f' % x)
def lastbd(mon):
    for i in range(4, -1, -1):
        d = mon + datetime.timedelta(days=i)
        if isbd(d):
            return d
    return None
def nth_bd(start, n):
    d = start
    c = 0
    while c < n:
        d = d + ONE
        if isbd(d):
            c += 1
    return d
try:
    today, hh, mi = parse_now()
    prods = get_products()[:3]
    if not prods:
        raise ValueError('no products')
    monday = today - datetime.timedelta(days=today.weekday())
    a1 = lastbd(monday)
    if a1 is None or a1 <= today:
        a1 = lastbd(monday + datetime.timedelta(days=7))
    n = len(prods)
    P = []
    for i, p in enumerate(prods):
        typ = str(p.get('type') or '')
        if typ == 'credit_card':
            phrase = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = float(p.get('minimum_payment'))
            fname = 'minimum payment'
        else:
            phrase = 'personal loan' if typ == 'personal_loan' else ('car loan' if typ == 'car_loan' else typ.replace('_', ' '))
            floor = float(p.get('instalment_amount'))
            fname = 'instalment amount'
        due = float(p.get('past_due'))
        late = int(float(p.get('days_late')))
        early = late <= 7
        dl = nth_bd(today, 12 if early else 7)
        pa1 = a1 if a1 <= dl else dl
        P.append(dict(k=i + 1, pid=str(p.get('product_id') or ''), phrase=phrase, floor=floor, fname=fname, due=due, late=late, early=early, dl=dl, a1=pa1))
    lp = lambda x: str(x['late']) + (' day' if x['late'] == 1 else ' days')
    sent = []
    for x in P:
        sent.append('Your ' + x['phrase'] + ' has a past-due amount of ' + money(x['due']) + ' and is ' + lp(x) + ' late.')
    if n == 1:
        opening = 'I am calling from the Freya Bank collections team about a late payment. ' + sent[0] + ' Can you make this payment today?'
        ask = 'Can you make this payment today?'
    else:
        opening = 'I am calling from the Freya Bank collections team about late payments on ' + str(n) + ' products. ' + ' '.join(sent) + ' Can you pay all of them today?'
        ask = 'Can you pay all of them today?'
    facts = ['Today: ' + sayiso(today) + '.', 'Number of late products: ' + str(n) + '. Handle them in this order:', '']
    for x in P:
        k = str(x['k'])
        facts.append('PRODUCT ' + k + ': ' + x['phrase'] + '. Tools: create_promise_p' + k + ' and add_note_p' + k + '.')
        facts.append('  Full past-due amount: ' + money(x['due']) + ' (tool amount ' + num(x['due']) + '). Days late: ' + str(x['late']) + '.')
        facts.append('  Floor (' + x['fname'] + '): ' + money(x['floor']) + ' (tool amount ' + num(x['floor']) + '). If only the floor is paid, the rest stays overdue.')
        facts.append('  Acceptable amounts: from ' + money(x['floor']) + ' up to ' + money(x['due']) + ', both included. Below ' + money(x['floor']) + ' cannot be recorded.')
        facts.append('  Deadline (latest promise date) for product ' + k + ': ' + sayiso(x['dl']) + '.')
        a1t = ('Attempt 1: propose the full past-due amount ' + money(x['due']) + ' on ' + say(x['a1']) + ' [' + x['a1'].isoformat() + ']. If the customer has already said the full amount of this product is too much, attempt 1 is the floor ' + money(x['floor']) + ' on ' + say(x['a1']) + ' instead.')
        if x['early']:
            facts.append('  Band: EARLY. Exactly ONE persuasion attempt for product ' + k + '. ' + a1t + ' After it is refused, product ' + k + ' is refused.')
        else:
            facts.append('  Band: LATE. Exactly TWO persuasion attempts for product ' + k + '. ' + a1t + ' Attempt 2: propose the floor ' + money(x['floor']) + ' on the deadline ' + say(x['dl']) + ' [' + x['dl'].isoformat() + ']. After attempt 2 is refused, product ' + k + ' is refused. Skip an attempt whose exact offer (same amount and same date) the customer already refused for this product.')
        facts.append('')
    end = max(max(x['dl'] for x in P) + datetime.timedelta(days=3), monday + datetime.timedelta(days=13))
    facts.append('CALENDAR (look up every date the customer names; "this <weekday>" and "next <weekday>" are labelled; the status is given per product):')
    d = monday
    while d <= end:
        lab = ''
        if d < monday + datetime.timedelta(days=7):
            lab = ' ("this ' + DN[d.weekday()] + '")'
        elif d < monday + datetime.timedelta(days=14):
            lab = ' ("next ' + DN[d.weekday()] + '")'
        if d < today:
            facts.append('- ' + sayiso(d) + lab + ': in the past, NOT allowed')
            d = d + ONE
            continue
        kind = 'business day' if isbd(d) else ('weekend' if d.weekday() >= 5 else 'bank holiday')
        parts = []
        for x in P:
            pre = ('product ' + str(x['k']) + ' ') if n > 1 else ''
            if d > x['dl']:
                parts.append(pre + 'AFTER its deadline -> use the deadline ' + say(x['dl']) + ' [' + x['dl'].isoformat() + ']')
            elif isbd(d):
                parts.append(pre + 'ALLOWED' + (' (today)' if d == today else '') + (' (its deadline)' if d == x['dl'] else ''))
            else:
                nb = nextbd(d)
                parts.append(pre + 'NOT allowed -> offer the next business day ' + say(nb) + ' [' + nb.isoformat() + ']')
        facts.append('- ' + sayiso(d) + lab + ': ' + kind + '. ' + '; '.join(parts))
        d = d + ONE
    vars['account_facts'] = '\n'.join(facts)
    vars['collection_opening'] = opening
    vars['today_ask'] = ask
    vars['n_products'] = str(n)
    vars['product_list'] = '; '.join('product ' + str(x['k']) + ' = ' + x['phrase'] for x in P)
    for x in P:
        k = str(x['k'])
        vars['pid_' + k] = x['pid']
        vars['phrase_' + k] = x['phrase']
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_facts'] = 'Account details missing.'
    vars['account_state'] = 'missing'
    vars['n_products'] = '0'
    vars['account_error'] = str(e)[:200]
'''

VERIFY_PRE = r'''
import re, datetime
MON = dict(jan=1, feb=2, mar=3, apr=4, may=5, jun=6, jul=7, aug=8, sep=9, oct=10, nov=11, dec=12)
try:
    b = config.get('body')
    if isinstance(b, dict):
        f = str(b.get('field') or '')
        a = str(b.get('answer') or '').strip()
        if f == 'phone_last4':
            dg = re.sub(r'\D', '', a)
            if len(dg) >= 4:
                b['answer'] = dg[-4:]
        elif f == 'date_of_birth':
            out = None
            m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', a)
            if m:
                out = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                low = a.lower()
                mon = None
                for k in MON:
                    if re.search(r'\b' + k, low):
                        mon = MON[k]
                        break
                nums = re.findall(r'\d+', low)
                if mon:
                    yr = [int(x) for x in nums if len(x) == 4]
                    dy = [int(x) for x in nums if len(x) <= 2]
                    if yr and dy:
                        out = (yr[0], mon, dy[0])
                elif len(nums) == 3:
                    if len(nums[0]) == 4:
                        out = (int(nums[0]), int(nums[1]), int(nums[2]))
                    else:
                        y = int(nums[2])
                        if y < 100:
                            y = y + (1900 if y > 30 else 2000)
                        out = (y, int(nums[1]), int(nums[0]))
            if out:
                datetime.date(out[0], out[1], out[2])
                b['answer'] = '%04d-%02d-%02d' % out
except Exception:
    pass
'''

VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if not isinstance(d, dict):
            d = dict()
            result['data'] = d
        left = d.get('wrong_answers_left')
        if d.get('hint') == 'day_month_swapped':
            msg = 'The day and the month look swapped. This does NOT count as a wrong answer. Ask the customer to say their date of birth again, saying the month as a word (for example: 14 March 1988). Then call verify_identity again.'
        elif d.get('all_verified') is True:
            msg = 'Both answers are correct. The identity is verified.'
        elif d.get('ok') is False or (d.get('verified') is None):
            msg = 'The answer could not be read. This does NOT count as a wrong answer. Ask the customer to say the same answer again (for a date of birth: day, month as a word, and year). Then call verify_identity again.'
        elif d.get('verified') is True:
            msg = 'Correct. The date of birth question is done. Now ask ONLY for the last four digits of the phone number on file.'
        elif str(left) == '0':
            msg = 'Wrong answer. No attempts are left. The check has failed. Say nothing about any account.'
        else:
            msg = 'WRONG answer: it does not match our records. Tell the customer it does not match and ask the SAME question again. Wrong answers left: ' + str(left) + '.'
        d['what_to_do_next'] = msg
except Exception:
    pass
'''

PROMISE_POST_T = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if not isinstance(d, dict):
            d = dict()
            result['data'] = d
        if d.get('ok') is True:
            d['what_to_do_next'] = 'Saved for product KK. Do not announce it (the result is announced automatically later). Next: call create_promise for the next agreed product that is not saved yet; when none is left, call add_note for every product without a promise; then call transition_to_wrap_up.'
        else:
            d['what_to_do_next'] = 'FAILED for product KK, nothing was saved. Do not speak to the customer. If this is the FIRST failure for product KK, call create_promise_pKK again now with exactly the same values. If create_promise_pKK has already failed once before in this call, do not try again: product KK gets add_note_pKK with reason service_error. Never say this promise is recorded.'
except Exception:
    pass
'''

NOTE_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            d['what_to_do_next'] = 'Note saved. Call add_note for the next product without a promise that has no note yet. When every such product has a note, call transition_to_wrap_up. Do not speak.'
except Exception:
    pass
'''

GENERIC_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
except Exception:
    pass
'''

CLOSE_PRE = r'''
try:
    b = config.get('body')
    if isinstance(b, dict):
        o = str(b.get('outcome') or '').strip()
        r = str(b.get('reason') or '').strip()
        if o in ('promise', 'paid') or (not r) or ('{' in r):
            b.pop('reason', None)
except Exception:
    pass
'''

for name, src in list(globals().items()):
    if name.isupper() and isinstance(src, str) and ("{{" in src or "}}" in src):
        raise SystemExit("double brace in " + name)

# ---------------------------------------------------------------- builders
HEADERS = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, path, body_props, required, description, retries=0, post=GENERIC_POST, pre=None, mapping=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(body_props)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BASE + path},
                "method": {"type": "string", "default": "POST"},
                "headers": HEADERS,
                "body": {"type": "object", "properties": props, "required": required},
            }},
        },
    }
    if post:
        t["post_process_code"] = post
    if pre:
        t["pre_process_code"] = pre
    if mapping:
        t["response_mapping"] = mapping
    return t


def transfer_tool(name, queue, description):
    return api_tool(name, "transfer_to_agent", {"queue": {"type": "string", "enum": [queue], "default": queue}}, [], description)


VERIFY = api_tool("verify_identity", "verify_identity", {
    "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
              "description": "Which question this answer is for: date_of_birth or phone_last4."},
    "answer": {"type": "string", "default": "{{answer}}",
               "description": "date_of_birth: the date as YYYY-MM-DD. A date said only in numbers is day, then month, then year. phone_last4: exactly four digits."},
}, ["field", "answer"], "Check ONE security answer. CALL it every time the customer gives an answer to a security question, with that single answer.",
    post=VERIFY_POST, pre=VERIFY_PRE)

def create_promise_tool(k):
    k = str(k)
    return api_tool("create_promise_p" + k, "create_promise", {
        "product_id": {"type": "string", "default": "{{pid_" + k + "}}"},
        "amount": {"type": "number", "default": "{{amount}}", "description": "The agreed amount for product " + k + " as a plain number, for example 455 or 45.5."},
        "date": {"type": "string", "default": "{{date}}", "description": "The agreed payment date for product " + k + " as YYYY-MM-DD, copied from the calendar."},
    }, ["amount", "date"], "Record the payment promise for PRODUCT " + k + " only. CALL it only after the customer clearly said yes to your read-back of all agreed promises.",
        post=PROMISE_POST_T.replace("KK", k))


NOTE_REASONS = ["refused", "hardship", "dispute", "paid", "service_error"]


def add_note_tool(k):
    k = str(k)
    return api_tool("add_note_p" + k, "add_note", {
        "product_id": {"type": "string", "default": "{{pid_" + k + "}}"},
        "reason": {"type": "string", "enum": NOTE_REASONS, "default": "{{reason}}",
                   "description": "Why product " + k + " ended without a promise. One of: refused (attempts used up, refused, or does not want to talk), hardship (illness, death in the family or job loss), dispute (says it is not theirs, never had it, or it was closed or paid off in the past), paid (says they already paid this past-due amount), service_error (create_promise failed twice)."},
    }, ["reason"], "Record why PRODUCT " + k + " ended without a promise. CALL it once, at the end, only for a product with no recorded promise. Never call it when the call is transferred.",
        post=NOTE_POST)

SCHEDULE = api_tool("schedule_callback", "schedule_callback", {
    "date": {"type": "string", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD."},
    "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour clock, for example 15:00."},
}, ["date", "time"], "Book a callback. CALL it as soon as the person gives a day and time that is inside the allowed callback window.")

T_SUPPORT = transfer_tool("transfer_support", "support", "Transfer to the customer support team. CALL it only when a customer with illness, a death in the family or job loss accepted your offer to be connected to customer support.")
T_RESTRUCT = transfer_tool("transfer_restructuring", "restructuring", "Transfer to the restructuring team. CALL it as soon as the customer asks for a new payment plan or lower instalments.")
T_HUMAN = transfer_tool("transfer_human", "general", "Transfer to a human agent. CALL it only when the customer asks for a human (or a real person) a second time after you asked once whether you could help.")

GET_ACCOUNT = api_tool("get_account", "get_account", {}, [], "Get the late products.", retries=2, post=None)

CLOSE_CALL = api_tool("close_call", "close_call", {
    "outcome": {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"],
                "default": "{{close_outcome}}",
                "description": "promise: a promise was recorded. paid: customer already paid. transferred: call was transferred. no_promise: verified customer, no promise. not_verified: identity check failed or was declined. not_reached: the customer was not reached."},
    "reason": {"type": "string", "default": "{{close_reason}}",
               "description": "transferred: restructuring, human or support. no_promise: refused, hardship, dispute or service_error. not_verified: failed or declined. not_reached: callback, no_callback, wrong_number, deceased or unclear. Empty for promise and paid."},
}, ["outcome"], "Record how the call ended.", post=None, pre=CLOSE_PRE)
CLOSE_CALL["config"]["alwaysRunsAt"] = ["end_of_call"]

nodes = {}


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def var_eq(target, desc, pairs):
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": [
        {"variable": v, "operator": "equals", "operand": o} for v, o in pairs]}}


def var_gt(target, desc, pairs):
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": [
        {"variable": v, "operator": "greater_than", "operand": o} for v, o in pairs]}}


def is_true(var):
    return [(var, "true"), (var, "True")]


def tool_transition(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def code_node(name, code, transitions, default):
    nodes[name] = {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": default,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                                          "parameters": {"type": "object", "properties": {
                                                              "code": {"type": "string", "default": code},
                                                              "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": transitions,
    }


def end_node(name, message):
    nodes[name] = {
        "name": name, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {"type": "function", "function": {"name": name, "handler": "__function__:end_call", "parameters": {
            "type": "object", "properties": {
                "message_mode": {"type": "string", "default": "custom"},
                "spoken_message": {"type": "string", "default": message}}}}},
    }


def closer(key, outcome, reason, message):
    bye = "bye_" + key
    code_node("close_" + key, "vars['close_outcome'] = '%s'\nvars['close_reason'] = '%s'\n" % (outcome, reason), [always(bye)], bye)
    end_node(bye, message)


def conv(name, task, tools=None, transitions=None, on_enter=None, extraction=None, max_turns=30, max_target=None, first_only=False):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools or [],
         "transitions": transitions or [], "on_enter": on_enter or {"type": "llm"},
         "max_node_turns": max_turns}
    if max_target:
        n["max_turn_transition"] = max_target
    if extraction:
        n["extraction_schema"] = extraction
    if first_only:
        n["on_enter_first_entry_only"] = True
    nodes[name] = n


GOODBYE = " Thank you for your time. Goodbye."
end_node("bye_promise", "Thank you for your time, {{title}} {{last_name}}. Goodbye.")
end_node("bye_final", "{{final_message}} Thank you for your time, {{title}} {{last_name}}. Goodbye.")
closer("account_error", "no_promise", "service_error", "I am sorry, I cannot reach your account details right now because of a technical problem." + GOODBYE)
closer("transfer_support", "transferred", "support", "Thank you. I am connecting you with our customer support team now. Goodbye.")
closer("transfer_restructuring", "transferred", "restructuring", "Thank you. I am connecting you with our restructuring team now. Goodbye.")
closer("transfer_human", "transferred", "human", "Thank you. I am connecting you with a colleague now. Goodbye.")
closer("failed", "not_verified", "failed", "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch." + GOODBYE)
closer("declined", "not_verified", "declined", "I understand. Without the security questions I cannot continue." + GOODBYE)
closer("callback", "not_reached", "callback", "Thank you, we will call back then. Thank you for your help. Goodbye.")
closer("no_callback", "not_reached", "no_callback", "Thank you, we will try again another time. Thank you for your help. Goodbye.")
closer("wrong_number", "not_reached", "wrong_number", "I apologise for the inconvenience." + GOODBYE)
closer("deceased", "not_reached", "deceased", "I am sorry for your loss. Thank you, goodbye.")
closer("unclear", "not_reached", "unclear", "I am sorry, I could not confirm who I am speaking with. We will try again later." + GOODBYE)

TRANSFER_ROUTES = [
    var_gt("close_transfer_support", "transferred to support", [("transfer_support_success_count", 0)]),
    var_gt("close_transfer_restructuring", "transferred to restructuring", [("transfer_restructuring_success_count", 0)]),
    var_gt("close_transfer_human", "transferred to a human", [("transfer_human_success_count", 0)]),
]

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is the caller. Speak English. Keep every turn to one or two short sentences. Address the customer as {{title}} {{last_name}}.
General rules:
- Never invent figures, dates, reasons or terms. If you cannot answer a question from what you were given, say you do not have that information.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam: say they can verify this call by phoning Freya Bank's customer service number, then continue.
- Never offer a discount, a waiver, an instalment plan or any term you were not given.
- When a rule says to call a tool, call the tool. Call one tool per message. After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing.
- Never say goodbye yourself: the closing words are spoken automatically when the call ends."""

# ---------------------------------------------------------------- opening
WHO_VALUES = ["confirmed", "someone_else", "wrong_number", "deceased", "refuses", "unclear"]


def who_schema(name):
    return [{"name": name, "type": "string", "enum_values": WHO_VALUES, "min_confidence": 0.5,
             "description": ("Who answered, judged from the person's LAST message only. "
                             "confirmed: the person says yes, that's me, speaking, or says the customer's own name ({{first_name}} {{last_name}}) as their own. "
                             "someone_else: a different person (relative, colleague, flatmate) answered, or says the customer is not available or not there. "
                             "wrong_number: says this number does not belong to the customer or they do not know the customer. "
                             "deceased: says the customer has died or passed away. "
                             "refuses: says they do not want to talk or are not interested. "
                             "unclear: anything else, such as hello, go ahead, who is this, what is this about, or a question.")}]


def who_routes(refuse_target, fallback):
    def r(t, v, var):
        return var_eq(t, "who answered: " + v, [(var, v)])
    return lambda var: [
        r("close_deceased", "deceased", var),
        r("close_wrong_number", "wrong_number", var),
        r("identity", "confirmed", var),
        r("third_party", "someone_else", var),
        r(refuse_target, "refuses", var),
        always(fallback),
    ]


code_node("setup", SETUP_CODE, [always("opening")], "opening")

conv("opening",
     "You have just asked whether you are speaking with {{title}} {{last_name}}. Do not say why you are calling. Do not call any tool in this turn. If the person asked a question, answer it briefly and ask again: \"Am I speaking with {{title}} {{last_name}}?\"",
     on_enter={"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
     extraction=who_schema("who1"),
     transitions=who_routes("opening_retry", "opening_retry")("who1"), max_turns=3, max_target="close_unclear")

conv("opening_retry",
     "You asked whether you are speaking with {{title}} {{last_name}} and did not get a clear yes. "
     "Do NOT say why you are calling and do not mention any account, debt, payment, collections or product. Do not call any tool in this turn.\n"
     "If the person asked a question (who is calling, robot, scam, what it is about), answer it in one short sentence without giving the reason for the call "
     "(you are Freya Bank's digital assistant; you can explain once you know you are speaking with the right person). "
     "Then ask one more time, exactly: \"Am I speaking with {{title}} {{last_name}}?\"",
     extraction=who_schema("who2"),
     transitions=who_routes("close_declined", "close_unclear")("who2"), max_turns=3, max_target="close_unclear")

# ---------------------------------------------------------------- third party
conv("third_party",
     "The person on the line is NOT {{title}} {{last_name}}. Your only job is to find a time when {{title}} {{last_name}} can be reached, and to book it.\n"
     "STRICT: Say nothing about why you are calling. Never mention an account, debt, payment, collections, product or amount, even if the person is a relative, offers to pay, or asks. "
     "If asked what it is about, say you can only discuss it with {{title}} {{last_name}}. Never ask this person any security question.\n\n"
     "CALLBACK WINDOW:\n{{callback_facts}}\n\n"
     "WHAT TO DO:\n"
     "1. Ask when {{title}} {{last_name}} can be reached (day and time). If the person gives only a day or a vague time, ask for the exact time.\n"
     "2. If the day and time are inside the window: call schedule_callback with the date (YYYY-MM-DD) and time (HH:MM, 24 hour). Do not speak before calling it.\n"
     "3. If what they offer is outside the window: say you can only call back today or on the next business day between 10:00 and 19:00 and ask ONCE for another time. "
     "If the second answer is also outside the window, or they cannot give any time: call transition_to_close_no_callback.\n"
     "4. If they say this number does not belong to {{title}} {{last_name}} or they do not know them: call transition_to_close_wrong_number.\n"
     "5. If they say {{title}} {{last_name}} has died: call transition_to_close_deceased immediately, with no text and no question (the condolence is spoken automatically).\n"
     "6. If schedule_callback fails, try it once more.",
     tools=[SCHEDULE],
     transitions=[
         var_eq("close_callback", "callback booked", is_true("schedule_callback_response.data.ok")),
         var_gt("close_no_callback", "callback booking failed twice", [("schedule_callback_failure_count", 1)]),
         tool_transition("close_no_callback", "CALL when the person gave a second time outside the callback window, or cannot or will not give any time."),
         tool_transition("close_wrong_number", "CALL when the person says this number does not belong to the customer or they do not know the customer."),
         tool_transition("close_deceased", "CALL immediately, with no text, when the person says the customer has died."),
     ], max_turns=12, max_target="close_no_callback")

# ---------------------------------------------------------------- identity
ID_TASK = ("The person confirmed they are {{title}} {{last_name}}. Your only job now is the security check. You do not discuss the reason for the call before it passes; "
           "do not mention any account, debt, payment, collections or product.\n"
           "1. Ask the date of birth first. When they answer, call verify_identity with field date_of_birth and the date as YYYY-MM-DD "
           "(convert words like \"fourteenth of March nineteen eighty-eight\" to 1988-03-14; a date given only in numbers is day, then month, then year). "
           "If they give only part of a date, ask for the rest before calling the tool.\n"
           "2. Only after the date of birth is correct, ask for the last four digits of the phone number on file and call verify_identity with field phone_last4.\n"
           "3. Every tool result has a what_to_do_next line: follow it exactly. A wrong answer is asked again. Never tell the customer an answer was correct when it was not.\n"
           "4. If the customer asks for a human: ask once whether you can help first. If they insist, call transfer_human.\n"
           "Ask one question at a time.")

ID_SCHEMA = lambda name: [{"name": name, "type": "string", "enum_values": ["answering", "declining"], "min_confidence": 0.6,
                           "description": "From the customer's LAST message only. declining: the customer refuses to answer the security question, says they do not want to give it, "
                                          "says they do not want to talk, or asks what the call is about / which account / why you need it INSTEAD of answering. "
                                          "answering: anything else, including giving an answer (right or wrong), a partial answer, or asking you to repeat."}]


def id_routes(decline_target, var):
    return [
        var_eq("fetch_account", "identity verified", is_true("verify_identity_response.data.all_verified")),
        var_eq("close_failed", "no wrong answers left", [("verify_identity_response.data.wrong_answers_left", "0")]),
        *TRANSFER_ROUTES[2:],
        var_eq(decline_target, "customer declines the security questions", [(var, "declining")]),
    ]


conv("identity", ID_TASK, tools=[VERIFY, T_HUMAN],
     on_enter={"type": "tts", "text": "Thank you. Before I continue, I need to ask you two security questions. First, what is your date of birth?"},
     extraction=ID_SCHEMA("id_decline1"), transitions=id_routes("identity_explain", "id_decline1"), max_turns=15, max_target="close_failed")

conv("identity_explain",
     "The customer did not answer a security question (they refused, or asked what the call is about instead). "
     "Explain once, in one sentence, that these questions protect their account and that you can only continue after them. "
     "Do not say why you are calling. Then ask the pending question again: the date of birth if it has not been verified yet, otherwise the last four digits of the phone number on file.\n\n" + ID_TASK,
     tools=[VERIFY, T_HUMAN], extraction=ID_SCHEMA("id_decline2"), transitions=id_routes("close_declined", "id_decline2"),
     max_turns=15, max_target="close_failed", first_only=False)

# ---------------------------------------------------------------- account
nodes["fetch_account"] = {
    "name": "fetch_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "account_setup",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": True,
    "pre_actions": [GET_ACCOUNT], "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [always("account_setup")],
}
code_node("account_setup", ACCOUNT_CODE, [
    var_eq("collection_1", "one product", [("n_products", "1")]),
    var_eq("collection_2", "two products", [("n_products", "2")]),
    var_eq("collection_3", "three products", [("n_products", "3")]),
    always("close_account_error")], "close_account_error")

COLLECTION_TASK = """The customer {{title}} {{last_name}} passed the security check. You have already told them, one sentence per product, which products are late, with the past-due amounts and days late, and asked: "{{today_ask}}"

ACCOUNT AND DATE FACTS (computed for you, trust them exactly):
{{account_facts}}

TOOL RULES: When a rule says to call a tool, call the tool. Call one tool per message. Each product has its own tools: create_promise_pN and add_note_pN, where N is the product number above ({{product_list}}). Never use the tool of one product for another.

HOW TO HANDLE THE PRODUCTS
A. Paying today: if the customer can pay everything today, the agreement is the full past-due amount of every product, today. If they can pay only some products today, those are agreed in full for today and you continue with the others. Never ask about today again.
B. Otherwise go through the products one at a time, in the order above. For each product that is not settled yet, open directly with its attempt 1 (for example: "For your <product>, could you pay the <amount> on <date>?"). Finish one product before you start the next. When you move on, name the next product.
C. For the product you are on:
   1. You propose every amount. Never ask the customer how much or which amount they will pay. When a date is agreed but no amount was named, propose the full past-due amount of that product (or its floor if the customer said its full amount is too much). If an amount sounds cut off or incomplete, ask them to repeat it; never guess.
   2. A date or an amount the customer proposes is NEVER a refusal. Check it against THIS product:
      - Date: look it up in the CALENDAR under this product. ALLOWED -> use it. NOT allowed (weekend or holiday) -> offer the next business day shown. AFTER its deadline -> say the latest date you can record for this product is its deadline and offer it. In the past -> ask for a day from today on.
      - Vague period ("next week", "end of the month", "when my salary comes"): ask ONCE for the exact day. If they still give no exact day, propose this product's deadline.
      - Amount from the floor up to the full amount (both included) -> accept it. Below the floor -> say it cannot be recorded and offer the floor once.
   3. If the customer says the full amount is too much: offer this product's floor ONCE, say in the same sentence that the rest stays overdue. Never offer the floor again as a new offer; after this the floor appears again only in this product's attempt 2 on the deadline, and in the read-back.
   4. A FLAT REFUSAL is a no with no date and no amount, a non-answer, refusing the floor, refusing the deadline, or not accepting the floor after a too-low amount. Each flat refusal uses the NEXT persuasion attempt of THIS product's ladder (attempts are counted per product). When this product has no attempt left, it is refused: say "Understood." and move on to the next product. Never repeat an offer (same amount and same date) already refused for this product.
   5. The customer says they already paid this product's past-due amount: say that payments can take one business day to appear. No promise for it (note reason paid). Move on.
   6. The customer says the product is not theirs, they never had it, or it was closed or paid off in the past: do not argue. No promise for it (note reason dispute). Move on.
D. ONE DATE FOR EVERYTHING: if the customer names one date for all products, use it for every product where it is allowed. For a product where that date is after its deadline, use that product's own deadline instead and say so clearly in the read-back. Weekend or holiday -> the next business day.
E. Illness, a death in the family or job loss: say one short sentence of sympathy, make NO persuasion attempt (for any product), and offer to connect them with the customer support team. If they accept, call transfer_support. If they decline, every product without an agreement ends with reason hardship. If they still name a date or an amount themselves, take that promise normally.
F. READ-BACK: when every product is settled (agreed, refused, paid, dispute or hardship) and at least one promise is agreed, read ALL agreed promises back together in one message: "To confirm: <product>, <amount> on <weekday day month>; <product>, <amount> on <weekday day month>. Do you confirm?" Ask for one confirmation only. If the customer changes a date or an amount, check it again and read everything back again.
G. RECORDING: after a clear yes, call create_promise_pN once for each agreed product, in product order, one per message, without speaking in between. Use the amount as a number and the date as YYYY-MM-DD from the calendar. Follow each what_to_do_next line. If one fails, call it once more; if it fails again, that product gets reason service_error and the others stay as they are.
H. NOTES: after the recording (or straight away if no promise was agreed), call add_note_pN once for every product that has NO recorded promise, with its reason: refused, hardship, dispute, paid or service_error. Do not speak in between.
I. Then call transition_to_wrap_up. Never say goodbye yourself, and never use the words "record" or "recorded" about a promise yourself: the result is announced automatically.

OTHER SITUATIONS
- A request for a new payment plan or lower instalments: describe no plan, record nothing more, add no notes, and call transfer_restructuring at once.
- A request for a human: ask once whether you can help first. If they insist, call transfer_human (no notes).
- The customer says a second time that they do not want to talk: every product without an agreement is refused; do steps F to I (if nothing is agreed, go straight to H).
- Never add a note when the call is being transferred.
- Never offer a discount, a waiver, an instalment plan or anything not written here."""


def collection_node(n):
    tools = [create_promise_tool(k) for k in range(1, n + 1)] + [add_note_tool(k) for k in range(1, n + 1)] + [T_SUPPORT, T_RESTRUCT, T_HUMAN]
    conv("collection_%d" % n, COLLECTION_TASK, tools=tools,
         on_enter={"type": "tts", "text": "Thank you, {{title}} {{last_name}}, you are verified. {{collection_opening}}"},
         transitions=[*TRANSFER_ROUTES,
                      tool_transition("wrap_up", "CALL when every product is settled, every agreed promise went through create_promise, and every product without a recorded promise has its add_note.")],
         max_turns=70, max_target="wrap_up")


for n in range(1, MAXP + 1):
    collection_node(n)

WRAP_CODE = r'''
import json
def money(x):
    x = round(float(x), 2)
    if abs(x - round(x)) < 0.005:
        return format(int(round(x)), ',')
    return format(x, ',.2f')
DN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def sayd(s):
    try:
        import datetime
        d = datetime.date.fromisoformat(str(s)[:10])
        return DN[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1]
    except Exception:
        return str(s)
def truthy(v):
    return str(v).strip().lower() == 'true'
try:
    runs = int(vars.get('wrap_runs') or 0) + 1
    vars['wrap_runs'] = runs
    n = int(vars.get('n_products') or 0)
    recorded, failed, missing, reasons = [], [], [], []
    for k in range(1, n + 1):
        k = str(k)
        ph = str(vars.get('phrase_' + k) or ('product ' + k))
        ok = truthy(vars.get('create_promise_p' + k + '_response.data.ok'))
        tried = vars.get('create_promise_p' + k + '_response.data.ok') is not None or vars.get('create_promise_p' + k + '_response.status') is not None
        note = str(vars.get('add_note_p' + k + '_args.reason') or '').strip()
        if ok:
            am = vars.get('create_promise_p' + k + '_args.amount')
            dt = vars.get('create_promise_p' + k + '_args.date')
            if am is not None and dt is not None:
                recorded.append('your ' + ph + ', ' + money(am) + ' on ' + sayd(dt))
            else:
                recorded.append('your ' + ph)
            continue
        if tried:
            failed.append(ph)
        if note in ('refused', 'hardship', 'dispute', 'paid', 'service_error'):
            reasons.append(note)
        else:
            missing.append('product ' + k + ' (' + ph + ')')
            reasons.append('service_error' if tried else 'refused')
    vars['missing_notes'] = ', '.join(missing)
    if missing and runs == 1:
        vars['wrap_state'] = 'missing_notes'
    else:
        parts = []
        if recorded:
            parts.append(('Your promise is recorded: ' if len(recorded) == 1 else 'Your promises are recorded: ') + '; '.join(recorded) + '.')
        if failed:
            parts.append('I am sorry, I could not record the promise for your ' + ' and your '.join(failed) + ' because of a technical problem.')
        if recorded:
            vars['close_outcome'] = 'promise'
            vars['close_reason'] = ''
            vars['promise_summary'] = ' '.join(parts)
            vars['final_message'] = ''
            vars['wrap_state'] = 'promise'
        else:
            nonpaid = [r for r in reasons if r != 'paid']
            if reasons and not nonpaid:
                vars['close_outcome'] = 'paid'
                vars['close_reason'] = ''
            else:
                vars['close_outcome'] = 'no_promise'
                vars['close_reason'] = nonpaid[0] if nonpaid else 'refused'
            fm = ' '.join(parts)
            if not fm:
                fm = 'I understand.'
            vars['final_message'] = fm
            vars['promise_summary'] = ''
            vars['wrap_state'] = 'final'
except Exception as e:
    vars['wrap_error'] = str(e)[:200]
    vars['close_outcome'] = 'no_promise'
    vars['close_reason'] = 'refused'
    vars['final_message'] = 'I understand.'
    vars['wrap_state'] = 'final'
'''

code_node("wrap_up", WRAP_CODE, [
    var_eq("fix_notes", "notes missing", [("wrap_state", "missing_notes")]),
    var_eq("post_promise", "at least one promise recorded", [("wrap_state", "promise")]),
    always("bye_final")], "bye_final")


def fix_notes_node(n):
    conv("fix_notes_%d" % n,
         "These products have neither a recorded promise nor a note yet: {{missing_notes}}. Do not speak to the customer. "
         "Call add_note_pN for each of them, one per message, with the reason that fits the conversation: refused, hardship, dispute, paid or service_error. "
         "Then call transition_to_wrap_up.",
         tools=[add_note_tool(k) for k in range(1, n + 1)],
         transitions=[tool_transition("wrap_up", "CALL when every listed product has its add_note.")],
         max_turns=3, max_target="wrap_up")


for n in range(1, MAXP + 1):
    fix_notes_node(n)
nodes["fix_notes"] = {
    "name": "fix_notes", "node_type": "code", "passthrough": True, "passthrough_default_transition": "wrap_up",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                                      "parameters": {"type": "object", "properties": {
                                                          "code": {"type": "string", "default": "vars['fix_route'] = str(vars.get('n_products') or '1')\n"},
                                                          "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [var_eq("fix_notes_%d" % n, "n products", [("n_products", str(n))]) for n in range(1, MAXP + 1)] + [always("wrap_up")],
}

conv("post_promise",
     "The customer has just been told which promises are recorded. "
     "If the customer wants to change or cancel a promise: say it cannot be changed in this call and that they can change it in the mobile app. "
     "If they ask for a new payment plan or lower instalments, call transfer_restructuring. If they ask for a human, ask once whether you can help; if they insist, call transfer_human. "
     "Otherwise answer briefly from what you know and ask if there is anything else. Never say goodbye yourself.",
     tools=[T_RESTRUCT, T_HUMAN, T_SUPPORT],
     on_enter={"type": "tts", "text": "Thank you. {{promise_summary}} You will receive a text message confirming this promise. Is there anything else I can help you with?"},
     extraction=[{"name": "more_help", "type": "string", "enum_values": ["nothing_else", "has_request"], "min_confidence": 0.5,
                  "description": "From the customer's LAST message. nothing_else: no further request, says no, that's all, thanks, or goodbye. has_request: asks or wants something."}],
     transitions=[*TRANSFER_ROUTES, var_eq("bye_promise", "nothing else", [("more_help", "nothing_else")])],
     max_turns=5, max_target="bye_promise")

wf = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "tools": [CLOSE_CALL],
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

# sanity: every target exists
for k, n in nodes.items():
    for t in n.get("transitions", []):
        assert t["target_node"] in nodes, (k, t["target_node"])
    for f in ("max_turn_transition", "passthrough_default_transition"):
        if n.get(f):
            assert n[f] in nodes, (k, n[f])

OUT.write_text(json.dumps(wf, indent=1))
print("wrote", OUT, len(nodes), "nodes")
