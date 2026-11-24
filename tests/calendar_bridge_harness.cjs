// Public synthetic Google API adapter for cross-language protocol tests only.
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const path = require('node:path');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let reads = 0;
const cache = new Map();
const source = fs.readFileSync(path.join(__dirname, '../infra/google-calendar/Bridge.gs'), 'utf8');
const key = 'ab'.repeat(32), connection = 'c'.repeat(64);
const sandbox = {
  Date: class extends Date { static now() { return 1000000; } },
  Utilities: {
    computeHmacSha256Signature: (body, secret) => [...crypto.createHmac('sha256', secret).update(body).digest()],
    base64Decode: value => Buffer.from(value, 'base64'),
    base64Encode: value => Buffer.from(value).toString('base64'),
    newBlob: value => ({getDataAsString: () => Buffer.from(value).toString('utf8')}),
    Charset: {UTF_8: 'UTF-8'},
    formatDate: date => new Intl.DateTimeFormat('sv-SE', {timeZone:'Europe/Moscow'}).format(date)
  },
  PropertiesService: {getScriptProperties: () => ({getProperty: name =>
    name === 'JARVIS_HMAC_KEY' ? key : connection})},
  CacheService: {getScriptCache: () => ({get: nonce => cache.get(nonce), put: (nonce, value) => cache.set(nonce, value)})},
  LockService: {getScriptLock: () => ({tryLock: () => !input.busy, releaseLock() {}})},
  CalendarApp: {getDefaultCalendar: () => ({getTimeZone: () => 'Europe/Moscow',
    getEvents(start, end, options) {
      reads++;
      if (input.provider_failure) throw new Error('private provider detail');
      if (options.max !== 51) throw new Error('unbounded read');
      return Array.from({length: input.event_count || 0}, () => ({
        getTitle: () => 'Public synthetic fixture', isAllDayEvent: () => !!input.all_day,
        getStartTime: () => new Date('2026-11-25T09:00:00Z'),
        getEndTime: () => new Date('2026-11-25T10:00:00Z')
      }));
    }})},
  ContentService: {MimeType: {JSON:'json'}, createTextOutput: value => ({
    setMimeType() {return this;}, text:value
  })}
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const event = {postData:{type:'application/json',contents:JSON.stringify(input.envelope)},queryString:input.query || ''};
const result = sandbox.doPost(event);
const repeated = input.repeat ? sandbox.doPost(event) : null;
process.stdout.write(JSON.stringify({response:JSON.parse(result.text), reads,
  repeated:repeated ? JSON.parse(repeated.text) : null}));
