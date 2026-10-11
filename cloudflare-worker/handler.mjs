// Fixture server, not business-policy enforcement. Exact organizer responses are immutable.
const PREFIX = '/voice/v1/';
const REQUIRED = {
  'cards.list': ['customerNo'],
  'cards.balance': ['cardNumber'],
  'statement.week.get': ['cardNumber'],
  'statement.week.decide': ['cardNumber', 'newStatementWeek', 'statementDay'],
  'statement.week.change': ['cardNumber', 'newStatementWeek', 'statementDay'],
  'contact.email.get': ['customerNo', 'intAddressInfoType'],
  'statement.pdf.send': ['customerNo', 'cardNumber', 'currencyType', 'statementDate', 'emailAddress'],
};
const NOT_FOUND = {
  'cards.list': ['FB_IVR_CHANNEL_102', 'Müşteriye ait geçerli kart bilgisi bulunamadı.'],
  'cards.balance': ['FB_IVR_CHANNEL_120', 'Kart bakiye servisi hatası: kart bulunamadı'],
  'statement.week.get': ['FB_IVR_CHANNEL_121', 'Kart bulunamadı'],
  'statement.pdf.send': ['FB_IVR_CHANNEL_107', 'Pdf dokümanı bulunamadı'],
};
const headers = { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' };
const json = (body, status = 200) => Response.json(body, { status, headers });
const own = (value, key) => value && Object.hasOwn(value, String(key)) ? value[String(key)] : undefined;

function error(code, message, status = 400) {
  const guid = crypto.randomUUID().replaceAll('-', '');
  return json({ result: { guid, returnCode: code, code, messageText: message, message,
    type: status === 404 ? 'WARNING' : 'ERROR',
    details: { guid, rootCause: status === 404 ? 'NotFoundException' : 'InvalidArguments', errorOrigin: 'mock' },
  } }, status);
}

export function createWorker(records, { sleep = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  const customers = new Map(records.customers.map(customer => [String(customer.customerNo), customer]));
  const cardServices = new Map();
  for (const service of ['cards.balance', 'statement.week.get', 'statement.week.decide', 'statement.week.change']) {
    const entries = new Map();
    for (const customer of records.customers) {
      for (const [card, entry] of Object.entries(customer.services[service] || {})) {
        if (entries.has(card)) throw new Error(`Duplicate fixture card: ${service} ${card}`);
        entries.set(card, entry);
      }
    }
    cardServices.set(service, entries);
  }
  return {
    async fetch(request) {
      const path = new URL(request.url).pathname;
      if (request.method === 'OPTIONS') return new Response(null, { headers: { ...headers,
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS', 'Access-Control-Allow-Headers': '*' } });
      if (request.method === 'GET' && path === '/health') return json({ status: 'ok', customers: customers.size });
      if (request.method === 'POST' && path === '/oauth2/token') {
        // Test environment ignores authentication. No real credentials are collected.
        return json({ access_token: 'synthetic-mock-token', token_type: 'Bearer', expires_in: 1800 });
      }
      const service = path.startsWith(PREFIX) ? path.slice(PREFIX.length) : '';
      if (!Object.hasOwn(REQUIRED, service)) return json({ error: 'Not found' }, 404);
      if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
      let body;
      try { body = await request.json(); } catch { return error('INVALID_ARGUMENTS_ERROR', 'Invalid JSON'); }
      const data = body?.data;
      if (!data || typeof data !== 'object' || Array.isArray(data)) return error('INVALID_ARGUMENTS_ERROR', 'data cannot be empty');
      for (const field of REQUIRED[service]) {
        if (data[field] === undefined || data[field] === null || String(data[field]).trim() === '') {
          return error('INVALID_ARGUMENTS_ERROR', `${field} cannot be empty`);
        }
      }
      let entry;
      if (cardServices.has(service)) {
        entry = cardServices.get(service).get(String(data.cardNumber));
        if (service === 'statement.week.decide' || service === 'statement.week.change') entry = own(entry, data.newStatementWeek);
      } else {
        entry = customers.get(String(data.customerNo))?.services[service];
      }
      if (!entry || typeof entry.http !== 'number' || !entry.response) {
        const missing = NOT_FOUND[service];
        return missing ? error(missing[0], missing[1], 404) : error('INVALID_ARGUMENTS_ERROR', 'No matching test record');
      }
      if (entry.delaySeconds) await sleep(entry.delaySeconds * 1000);
      return json(entry.response, entry.http);
    },
  };
}
