import freya, json, sys
d = json.load(open(sys.argv[1]))
for rep, cid in [(int(x.split(':')[0]), x.split(':')[1]) for x in sys.argv[2:]]:
    r = [x for x in d['all_rows'][rep] if x['id'] == cid][0]
    print('=====', cid, 'rep', rep, r['failed'])
    for m in freya.get_call(r['call_id'])['messages']:
        role = m.get('role'); t = m.get('message') or m.get('content') or ''
        if role in ('user', 'assistant', 'bot'): print(role.upper() + ':', str(t)[:500])
        elif "function_call_start" in str(m.get("message")) and "code_exec" not in str(m.get("message")) and "api_call" not in str(m.get("message")): print('  [' + str(role) + ']', json.dumps({k: v for k, v in m.items() if k not in ('role', 'time', 'secondsFromStart', 'endTime')})[:400])
