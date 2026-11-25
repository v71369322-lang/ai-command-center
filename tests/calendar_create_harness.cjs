// Synthetic, in-memory Google API; no credentials or network are used.
const fs = require('node:fs'), vm = require('node:vm'), crypto = require('node:crypto');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const events = input.events || {};
let reads = 0, writes = 0;
const key = 'ab'.repeat(32), connection = 'c'.repeat(64);
function normalized(event) {
  if (!input.normalize_times || !event) return event;
  const result = JSON.parse(JSON.stringify(event));
  for(const field of ['start','end']) {
    result[field].dateTime = new Date(result[field].dateTime).toISOString();
    delete result[field].timeZone;
  }
  return result;
}
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
  Calendar:{Events:{
    list(calendar, options) {
      reads++;
      if (calendar !== 'synthetic@group.calendar.google.com' || options.maxResults !== 2 ||
          options.showDeleted !== false || options.singleEvents !== true) throw Error('unbounded lookup');
      if(input.provider_failure) throw Error('private provider failure');
      if (!Array.isArray(options.privateExtendedProperty) || options.privateExtendedProperty.length !== 1)
        throw Error('lookup binding');
      const draft = options.privateExtendedProperty[0].split('=')[1];
      return {items:Object.values(events).filter(e => e.extendedProperties.private.commanderDraftId === draft).map(normalized)};
    },
    insert(d, calendar, options) {
      if (calendar !== 'synthetic@group.calendar.google.com' || options.sendUpdates !== 'none' ||
          options.supportsAttachments !== false || d.attendees.length || d.guestsCanInviteOthers ||
          d.guestsCanModify) throw Error('unsafe insert');
      if(events[d.id]) throw Error('409 conflict');
      if(input.provider_failure) throw Error('private provider failure');
      writes++; const event = {...d,status:'confirmed',etag:'"synthetic-etag"'};events[d.id]=event;
      if(input.lose_response) throw Error('timeout after commit');
      return normalized(event);
    }
  }},
  ContentService:{MimeType:{JSON:'json'},createTextOutput:text=>({text,setMimeType(){return this;}})}
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,
  '../infra/google-calendar-create/Bridge.gs'),'utf8'),sandbox);
const responses = input.envelopes.map(envelope => JSON.parse(sandbox.doPost({
  postData:{type:'application/json',contents:JSON.stringify(envelope)},queryString:''}).text));
process.stdout.write(JSON.stringify({responses,events,reads,writes}));
