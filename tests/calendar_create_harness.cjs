// Synthetic, in-memory Google API; no credentials or network are used.
const fs = require('node:fs'), vm = require('node:vm'), crypto = require('node:crypto');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const events = input.events || {};
let reads = 0, writes = 0;
const key = 'ab'.repeat(32), connection = 'c'.repeat(64);
const sandbox = {
  Date: class extends Date { static now() { return 1000000; } },
  Utilities: {
    computeHmacSha256Signature: (body, secret) => [...crypto.createHmac('sha256', secret).update(body).digest()],
    computeDigest: (_, body) => [...crypto.createHash('sha256').update(body).digest()],
    DigestAlgorithm:{SHA_256:'sha256'}, Charset:{UTF_8:'UTF-8'},
    base64Decode: value => Buffer.from(value, 'base64'), base64Encode: value => Buffer.from(value).toString('base64'),
    newBlob: value => ({getDataAsString: () => Buffer.from(value).toString('utf8')})
  },
  PropertiesService:{getScriptProperties: () => ({getProperty: name => ({JARVIS_HMAC_KEY:key,
    JARVIS_CONNECTION:connection,JARVIS_CALENDAR_ID:'synthetic@group.calendar.google.com',
    JARVIS_CREATE_ENABLED:input.disabled?'0':'1'})[name]})},
  LockService:{getScriptLock: () => ({tryLock: () => !input.busy,releaseLock(){}})},
  ScriptApp:{getOAuthToken: () => 'PUBLIC_SYNTHETIC_FIXTURE'},
  UrlFetchApp:{fetch(url, options) {
    const parsed = new URL(url);
    if (parsed.origin !== 'https://www.googleapis.com' || options.followRedirects !== false ||
        options.validateHttpsCertificates !== true ||
        !parsed.pathname.startsWith('/calendar/v3/calendars/synthetic%40group.calendar.google.com/events'))
      throw Error('unsafe request');
    let code, body;
    if (options.method === 'get') {
      reads++; const id = parsed.pathname.split('/').pop(); body = events[id]; code = body?200:404;
    } else if (options.method === 'post') {
      if (parsed.searchParams.get('sendUpdates') !== 'none') throw Error('notifications');
      const d = JSON.parse(options.payload);
      if (d.attendees.length || d.guestsCanInviteOthers || d.guestsCanModify) throw Error('attendees');
      if (events[d.id]) {code=409;body={};}
      else {
        writes++;body={...d,status:'confirmed',etag:'"synthetic-etag"'};events[d.id]=body;code=201;
        if (input.lose_response) throw Error('timeout after commit');
      }
    } else throw Error('arbitrary method');
    if (input.provider_failure) {code=503;body={private:'never expose'};}
    return {getResponseCode:()=>code,getContentText:()=>JSON.stringify(body || {})};
  }},
  ContentService:{MimeType:{JSON:'json'},createTextOutput:text=>({text,setMimeType(){return this;}})}
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,
  '../infra/google-calendar-create/Bridge.gs'),'utf8'),sandbox);
const responses = input.envelopes.map(envelope => JSON.parse(sandbox.doPost({
  postData:{type:'application/json',contents:JSON.stringify(envelope)},queryString:''}).text));
process.stdout.write(JSON.stringify({responses,events,reads,writes}));
