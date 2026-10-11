import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createWorker } from './handler.mjs';
import deployedWorker from './worker.js';

const fixtures = JSON.parse(await readFile(new URL('../cases/Build%20the%20Builder%20-%20Final%20Case/test-environment/test-customers.json', import.meta.url), 'utf8'));
const delays = [];
const worker = createWorker(fixtures, { sleep: async ms => { delays.push(ms); } });
const request = (service, data) => new Request('https://mock.test/voice/v1/' + service,
  { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data, call: { lang: 'tr' } }) });

export function fixtureRequests() {
  const rows = [];
  for (const customer of fixtures.customers) {
    for (const [service, records] of Object.entries(customer.services)) {
      if (['cards.list', 'contact.email.get', 'statement.pdf.send'].includes(service)) {
        const card = customer.services['cards.list'].response.data?.cards?.[0]?.cardNumber || 'not-used';
        const balance = customer.services['cards.balance']?.[card]?.response.data;
        rows.push({ service, data: { customerNo: customer.customerNo, cardNumber: card, aiFlow: 'CardOps',
          intAddressInfoType: 'E', currencyType: 'TL', statementDate: balance?.statementDate || '01.01.2026',
          emailAddress: customer.services['contact.email.get']?.response.data?.ibanEmail || 'test@example.com' }, entry: records });
      } else {
        for (const [cardNumber, value] of Object.entries(records)) {
          if (['statement.week.decide', 'statement.week.change'].includes(service)) {
            for (const [newStatementWeek, entry] of Object.entries(value)) rows.push({ service,
              data: { cardNumber, newStatementWeek, statementDay: customer.services['statement.week.get']?.[cardNumber]?.response.data?.statementDay || 1 }, entry });
          } else rows.push({ service, data: { cardNumber }, entry: value });
        }
      }
    }
  }
  return rows;
}

test('every fixture response matches its body and HTTP status, with delay metadata kept out of body', async () => {
  let count = 0;
  for (const { service, data, entry } of fixtureRequests()) {
    const response = await worker.fetch(request(service, data));
    assert.equal(response.status, entry.http, `${service} ${JSON.stringify(data)}`);
    assert.deepEqual(await response.json(), entry.response, service);
    count++;
  }
  console.log(`Verified ${count} fixture responses for ${fixtures.customers.length} customers`);
  assert.ok(delays.some(ms => ms > 10000));
});

test('numeric customer/week inputs and repeated mutations preserve fixture responses', async () => {
  const row = fixtureRequests().find(row => row.service === 'statement.week.change');
  const data = { ...row.data, newStatementWeek: Number(row.data.newStatementWeek) };
  for (let i = 0; i < 2; i++) assert.deepEqual(await (await worker.fetch(request(row.service, data))).json(), row.entry.response);
  const customer = fixtures.customers[0];
  assert.deepEqual(await (await worker.fetch(request('cards.list', { customerNo: Number(customer.customerNo) }))).json(), customer.services['cards.list'].response);
});

test('unknown and malformed requests use contract errors, never a default customer', async () => {
  for (const [service, expected] of [['cards.list', 'FB_IVR_CHANNEL_102'], ['cards.balance', 'FB_IVR_CHANNEL_120'],
    ['statement.week.get', 'FB_IVR_CHANNEL_121'], ['statement.pdf.send', 'FB_IVR_CHANNEL_107']]) {
    const response = await worker.fetch(request(service, { customerNo: 'unknown', cardNumber: 'unknown', currencyType: 'TL', statementDate: '01.01.2026', emailAddress: 'a@b.test' }));
    const body = await response.json();
    assert.equal(response.status, 404); assert.equal(body.result.code, expected); assert.equal(body.data, undefined);
  }
  for (const data of [{}, { customerNo: '' }, { customerNo: '{{customerNumber}}' }]) {
    const response = await worker.fetch(request('cards.list', data));
    assert.ok(response.status >= 400);
  }
  const response = await worker.fetch(request('statement.week.change', { cardNumber: 'unknown', newStatementWeek: 2, statementDay: 1 }));
  assert.equal(response.status, 400);
});

test('standalone deployable Worker contains the complete generated table', async () => {
  for (const row of fixtureRequests().filter(row => !row.entry.delaySeconds)) {
    const response = await deployedWorker.fetch(request(row.service, row.data));
    assert.equal(response.status, row.entry.http);
    assert.deepEqual(await response.json(), row.entry.response);
  }
});

test('deployed code really waits for the delayed fixture', async () => {
  const row = fixtureRequests().find(row => row.entry.delaySeconds);
  const started = performance.now();
  const response = await deployedWorker.fetch(request(row.service, row.data));
  assert.ok(performance.now() - started >= row.entry.delaySeconds * 1000 - 50);
  assert.equal(response.status, row.entry.http);
  assert.deepEqual(await response.json(), row.entry.response);
});
