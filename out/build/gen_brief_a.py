"""Generate out/brief-a.workflow.json for Brief A (Freya Bank, one product)."""
import json, pathlib

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
OUT = pathlib.Path(__file__).resolve().parent.parent / "brief-a.workflow.json"

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
try:
    today, hh, mi = parse_now()
    prods = get_products()
    p = prods[0]
    typ = str(p.get('type') or '')
    pid = str(p.get('product_id') or '')
    due = float(p.get('past_due'))
    late = int(float(p.get('days_late')))
    if typ == 'credit_card':
        phrase = 'credit card ending ' + str(p.get('card_last4') or '')
        floor = float(p.get('minimum_payment'))
        fname = 'minimum payment'
    else:
        phrase = 'personal loan' if typ == 'personal_loan' else ('car loan' if typ == 'car_loan' else typ.replace('_', ' '))
        floor = float(p.get('instalment_amount'))
        fname = 'instalment amount'
    early = late <= 7
    n = 12 if early else 7
    deadline = today
    c = 0
    while c < n:
        deadline = deadline + ONE
        if isbd(deadline):
            c += 1
    monday = today - datetime.timedelta(days=today.weekday())
    a1 = lastbd(monday)
    if a1 is None or a1 <= today:
        a1 = lastbd(monday + datetime.timedelta(days=7))
    if a1 > deadline:
        a1 = deadline
    end = max(deadline + datetime.timedelta(days=3), monday + datetime.timedelta(days=13))
    cal = []
    d = monday
    while d <= end:
        lab = ''
        if d < monday + datetime.timedelta(days=7):
            lab = ' ("this ' + DN[d.weekday()] + '")'
        elif d < monday + datetime.timedelta(days=14):
            lab = ' ("next ' + DN[d.weekday()] + '")'
        if d < today:
            st = 'in the past: NOT allowed'
        elif d > deadline:
            st = 'after the deadline: NOT allowed, offer the deadline ' + say(deadline) + ' instead'
        elif isbd(d):
            st = 'ALLOWED' + (' (today)' if d == today else '') + (' (this is the deadline)' if d == deadline else '')
        else:
            kind = 'weekend' if d.weekday() >= 5 else 'bank holiday'
            st = kind + ': NOT allowed, offer the next business day ' + say(nextbd(d)) + ' instead'
        cal.append('- ' + sayiso(d) + lab + ': ' + st)
        d = d + ONE
    a1_amt_note = ('the full past-due amount ' + money(due) + ' on ' + say(a1) + '. BUT if the customer has said at any point that the full amount is too much (including refusing the floor afterwards), attempt 1 is the ' + fname + ' ' + money(floor) + ' on ' + say(a1) + ' instead, and you never propose the full amount again')
    if early:
        ladder = ('Band: EARLY (' + str(late) + ' days late). You have exactly ONE persuasion attempt.\n'
                  'Attempt 1: propose ' + a1_amt_note + '.\n'
                  'If the customer refuses attempt 1 (or gives another flat refusal after it), there is no attempt left: end the call as refused.')
    else:
        ladder = ('Band: LATE (' + str(late) + ' days late). You have exactly TWO persuasion attempts.\n'
                  'Attempt 1: propose ' + a1_amt_note + '.\n'
                  'Attempt 2: propose the ' + fname + ' ' + money(floor) + ' on the deadline ' + say(deadline) + '.\n'
                  'If the customer refuses attempt 2 (or gives another flat refusal after it), there is no attempt left: end the call as refused. Skip an attempt whose exact offer (same amount and same date) the customer already refused.')
    facts = [
        'Product: ' + phrase + ' (product_id ' + pid + ').',
        'Full past-due amount: ' + money(due) + ' (create_promise amount ' + num(due) + ').',
        'Days late: ' + str(late) + '.',
        'Floor (' + fname + '): ' + money(floor) + ' (create_promise amount ' + num(floor) + '). The rest stays overdue if only the floor is paid.',
        'Acceptable amounts: from ' + money(floor) + ' up to ' + money(due) + ', both included. Below ' + money(floor) + ' cannot be recorded. More than ' + money(due) + ' is not needed.',
        'Today: ' + sayiso(today) + '.',
        'Deadline (latest promise date): ' + sayiso(deadline) + '.',
        ladder,
        '',
        'CALENDAR (use it for every date the customer names; "this <weekday>" and "next <weekday>" are labelled):',
    ] + cal
    vars['account_facts'] = '\n'.join(facts)
    vars['product_id'] = pid
    vars['product_phrase'] = phrase
    vars['past_due_text'] = money(due)
    vars['late_phrase'] = str(late) + (' day' if late == 1 else ' days')
    vars['deadline_say'] = say(deadline)
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_facts'] = 'Account details missing.'
    vars['account_state'] = 'missing'
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

PROMISE_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if not isinstance(d, dict):
            d = dict()
            result['data'] = d
        if d.get('ok') is True:
            d['what_to_do_next'] = 'The promise is recorded.'
        else:
            d['what_to_do_next'] = 'FAILED, nothing was saved. Do not speak to the customer now. Call create_promise again immediately with exactly the same values. Never say the promise is recorded.'
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

CREATE_PROMISE = api_tool("create_promise", "create_promise", {
    "product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id from the account facts."},
    "amount": {"type": "number", "default": "{{amount}}", "description": "The agreed amount as a plain number, for example 455 or 45.5."},
    "date": {"type": "string", "default": "{{date}}", "description": "The agreed payment date as YYYY-MM-DD, copied from the calendar."},
}, ["amount", "date"], "Record the payment promise. CALL it only right after the customer clearly said yes to your read-back of product, amount and date.",
    post=PROMISE_POST)

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
closer("promise", "promise", "", "Thank you for your time, {{title}} {{last_name}}. Goodbye.")
closer("paid", "paid", "", "Thank you for letting me know. Payments can take one business day to appear on your account, so I will not take a promise today." + GOODBYE)
closer("dispute", "no_promise", "dispute", "I understand. I will not take a promise today." + GOODBYE)
closer("refused", "no_promise", "refused", "I understand." + GOODBYE)
closer("hardship", "no_promise", "hardship", "I understand. Take care." + GOODBYE)
closer("service_error", "no_promise", "service_error", "I am sorry, I could not record your promise because of a technical problem." + GOODBYE)
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
code_node("account_setup", ACCOUNT_CODE, [var_eq("collection", "account ready", [("account_state", "ok")]), always("close_account_error")], "close_account_error")

COLLECTION_TASK = """The customer {{title}} {{last_name}} passed the security check. You have already said you are calling from the collections team about the late payment on their {{product_phrase}} ({{past_due_text}}, {{late_phrase}} late) and asked: "Can you make this payment today?"

ACCOUNT AND DATE FACTS (computed for you, trust them exactly):
{{account_facts}}

HOW TO GET THE PROMISE
1. You propose every amount. Never ask the customer how much or which amount they will pay. When a date is agreed but no amount was named, propose the full past-due amount (or the floor if the customer said the full amount is too much). If an amount the customer says sounds cut off or incomplete, ask them to repeat it; never guess.
2. A date or an amount the customer proposes is NEVER a refusal. Check it:
   - Date: look it up in the CALENDAR. ALLOWED -> use it. Weekend or bank holiday not after the deadline -> offer the next business day shown. After the deadline -> say the latest date you can record is the deadline and offer it. In the past -> ask for a day from today on.
   - Vague period ("next week", "end of the month", "when my salary comes"): ask ONCE for the exact day. If they still give no exact day, propose the deadline.
   - Amount from the floor up to the full amount (both included) -> accept it. Below the floor -> say it cannot be recorded and offer the floor once.
3. If the customer says the full amount is too much: offer the floor ONCE, in the same sentence say that the rest stays overdue, and ask if they can pay it today. Never offer the floor a second time as a new offer; after this, the floor appears again only as part of a persuasion attempt, where you only move the DATE and do NOT say the amount again: "Could you make that payment on <date> instead?". Name the floor amount again only in the read-back and in attempt 2 on the deadline.
4. A FLAT REFUSAL is a no with no date and no amount (for example "no, I can't pay today"), a non-answer, refusing the floor, refusing the deadline, or not accepting the floor after a too-low amount. Each flat refusal moves to the NEXT persuasion attempt in the band ladder above. When no attempt is left, call transition_to_close_refused. Never repeat an offer (same amount and same date) the customer already refused. When you offer the floor, say that the rest stays overdue.
   If the customer asks how much they should or can pay, do not refuse to answer: state the amount you are proposing now.
5. Illness, a death in the family or job loss: say one short sentence of sympathy, make NO persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_support. If they decline, call transition_to_close_hardship. If they still name a date or an amount themselves, take the promise normally.
6. When a date and an amount are agreed, read back: "To confirm: <product>, <amount> on <weekday day month>. Do you confirm?" Call create_promise only after a clear yes, with product_id, the amount as a number and the date as YYYY-MM-DD from the calendar. If they change the date or amount, check it again and read back again.
7. Never use the words "recorded" or "record" about the promise yourself; success is announced automatically after create_promise succeeds. If create_promise fails, follow its what_to_do_next line: call create_promise again at once, without speaking and without asking the customer to confirm again.

OTHER SITUATIONS
- The customer says they already paid this past-due amount: call transition_to_close_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, call transition_to_close_dispute.
- A request for a new payment plan or lower instalments: describe no plan, call transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_human.
- The customer says a second time that they do not want to talk: call transition_to_close_refused.
- Never offer a discount, a waiver, an instalment plan or anything not written here."""

COLLECTION_TOOL_TRANSITIONS = [
    tool_transition("close_refused", "CALL when every persuasion attempt of the band has been refused, or the customer said twice they do not want to talk."),
    tool_transition("close_hardship", "CALL when a customer with illness, a death in the family or job loss declined the offer to connect with customer support and named no date or amount."),
    tool_transition("close_paid", "CALL when the customer says they already paid this past-due amount."),
    tool_transition("close_dispute", "CALL when the customer says the debt is not theirs, they never had the product, or it was closed or paid off in the past."),
]

conv("collection", COLLECTION_TASK, tools=[CREATE_PROMISE, T_SUPPORT, T_RESTRUCT, T_HUMAN],
     on_enter={"type": "tts", "text": "Thank you, {{title}} {{last_name}}, you are verified. I am calling from the Freya Bank collections team about a late payment on your {{product_phrase}}. The past-due amount is {{past_due_text}}, and it is {{late_phrase}} late. Can you make this payment today?"},
     transitions=[
         var_eq("promise_saved", "promise recorded", is_true("create_promise_response.data.ok")),
         var_gt("close_service_error", "create_promise failed twice", [("create_promise_failure_count", 1), ("create_promise_success_count", 1)]),
         {"target_node": "close_service_error", "description": "create_promise failed twice (mixed)", "condition": {"logic": "or", "conditions": [
             {"logic": "and", "conditions": [
                 {"variable": "create_promise_failure_count", "operator": "greater_than", "operand": 0},
                 {"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}]}]}},
         *TRANSFER_ROUTES,
         *COLLECTION_TOOL_TRANSITIONS,
     ], max_turns=40, max_target="close_refused")

# merge the two service-error transitions into one (same target would be merged anyway)
coll = nodes["collection"]["transitions"]
coll[1]["condition"]["conditions"].append(coll[2]["condition"]["conditions"][0])
del coll[2]

code_node("promise_saved", "vars['close_outcome'] = 'promise'\nvars['close_reason'] = ''\n", [always("post_promise")], "post_promise")

conv("post_promise",
     "The payment promise is recorded and you have told the customer. "
     "If the customer wants to change or cancel the promise: say it cannot be changed in this call and that they can change it in the mobile app. "
     "If they ask for a new payment plan or lower instalments, call transfer_restructuring. If they ask for a human, ask once whether you can help; if they insist, call transfer_human. "
     "Otherwise answer briefly and ask if there is anything else.",
     tools=[T_RESTRUCT, T_HUMAN, T_SUPPORT],
     on_enter={"type": "tts", "text": "Thank you. Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
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
