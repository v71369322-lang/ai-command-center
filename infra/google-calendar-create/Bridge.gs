/** Separate opt-in create/get bridge. Never update/delete/invite. */
const JARVIS_CREATE_PROTOCOL = 'jarvis-calendar-create-v1';
function jarvisMac_(payload, key, purpose) {
  return Utilities.computeHmacSha256Signature(purpose + '\n' + payload, key)
    .map(b => ('0' + ((b + 256) % 256).toString(16)).slice(-2)).join('');
}
function jarvisEqual_(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i++) mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return mismatch === 0;
}
function jarvisKeys_(value, names) {
  return value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join(',') === names.slice().sort().join(',');
}
function jarvisHash_(document) {
  const sorted = {};
  Object.keys(document).sort().forEach(k => { sorted[k] = document[k]; });
  const canonical = JSON.stringify(sorted).replace(/[\u007f-\uffff]/g,
    c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, canonical, Utilities.Charset.UTF_8)
    .map(b => ('0' + ((b + 256) % 256).toString(16)).slice(-2)).join('');
}
function jarvisDocument_(d, hash) {
  if (!jarvisKeys_(d, ['title','start','end','timezone','note','telegram_reminder_minutes']) ||
      typeof d.title !== 'string' || d.title !== d.title.trim() || Array.from(d.title).length < 1 ||
      Array.from(d.title).length > 120 || typeof d.note !== 'string' || Array.from(d.note).length > 1000 ||
      d.timezone !== 'Europe/Moscow' || !Number.isInteger(d.telegram_reminder_minutes) ||
      d.telegram_reminder_minutes < 5 || d.telegram_reminder_minutes > 1440 ||
      !/^[a-f0-9]{64}$/.test(hash) || jarvisHash_(d) !== hash) throw new Error('document');
  const iso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+03:00$/;
  if (typeof d.start !== 'string' || typeof d.end !== 'string' || !iso.test(d.start) || !iso.test(d.end))
    throw new Error('time');
  const start = new Date(d.start), end = new Date(d.end);
  if (!Number.isFinite(+start) || !Number.isFinite(+end) || end <= start || end-start > 86400000)
    throw new Error('interval');
  const local = date => new Date(+date + 3 * 3600000).toISOString().slice(0,19) + '+03:00';
  if (local(start) !== d.start || local(end) !== d.end) throw new Error('wall_time');
}
function doGet() {
  return ContentService.createTextOutput('{"error":"unavailable"}').setMimeType(ContentService.MimeType.JSON);
}
function jarvisGoogle_(calendar, draftId, method, body) {
  let event;
  if (method === 'get') {
    const result = Calendar.Events.list(calendar, {privateExtendedProperty:'commanderDraftId=' + draftId,
      maxResults:2,showDeleted:false,singleEvents:true});
    const items = result.items || [];
    if (!Array.isArray(items) || items.length > 1 || result.nextPageToken) throw new Error('ambiguous');
    event = items.length ? items[0] : null;
  } else if (method === 'create') {
    event = Calendar.Events.insert(body, calendar, {sendUpdates:'none',supportsAttachments:false});
  } else { throw new Error('method'); }
  if (JSON.stringify(event).length > 20000) throw new Error('provider_size');
  return event;
}
function jarvisExact_(event, request) {
  const d = request.document, id = request.draft_id.replace(/-/g, '');
  const p = event && event.extendedProperties && event.extendedProperties.private;
  if (!event || event.id !== id || event.status !== 'confirmed' || event.summary !== d.title ||
      (event.description || '') !== d.note || typeof event.etag !== 'string' ||
      !event.start || !event.end || event.start.timeZone !== d.timezone || event.end.timeZone !== d.timezone ||
      +new Date(event.start.dateTime) !== +new Date(d.start) ||
      +new Date(event.end.dateTime) !== +new Date(d.end) ||
      !jarvisKeys_(p, ['commanderDraftId','commanderDocumentHash']) ||
      p.commanderDraftId !== request.draft_id || p.commanderDocumentHash !== request.document_hash ||
      (event.attendees && event.attendees.length) || event.recurrence || event.recurringEventId ||
      !event.reminders || event.reminders.useDefault !== false ||
      !Array.isArray(event.reminders.overrides) || event.reminders.overrides.length !== 1 ||
      event.reminders.overrides[0].method !== 'popup' ||
      event.reminders.overrides[0].minutes !== d.telegram_reminder_minutes) throw new Error('event_mismatch');
  return {id, etag:event.etag, status:'confirmed', summary:d.title, description:d.note,
    start:{dateTime:d.start,timeZone:d.timezone},end:{dateTime:d.end,timeZone:d.timezone},
    extendedProperties:{private:p}};
}
function doPost(e) {
  try {
    if (!e || !e.postData || e.postData.type !== 'application/json' ||
        typeof e.postData.contents !== 'string' || e.postData.contents.length > 16000 || e.queryString)
      throw new Error('request');
    const props = PropertiesService.getScriptProperties();
    const key = props.getProperty('JARVIS_HMAC_KEY'), connection = props.getProperty('JARVIS_CONNECTION');
    const calendar = props.getProperty('JARVIS_CALENDAR_ID');
    if (props.getProperty('JARVIS_CREATE_ENABLED') !== '1' || !/^[a-f0-9]{64}$/.test(key || '') ||
        !/^[a-f0-9]{64}$/.test(connection || '') || !/^[A-Za-z0-9_.@-]{1,256}$/.test(calendar || '') ||
        calendar === 'primary')
      throw new Error('configuration');
    const signed = JSON.parse(e.postData.contents);
    if (!jarvisKeys_(signed, ['payload','signature']) || typeof signed.payload !== 'string' ||
        signed.payload.length > 14000 || !/^[a-f0-9]{64}$/.test(signed.signature || '') ||
        !jarvisEqual_(signed.signature, jarvisMac_(signed.payload, key, 'JARVIS_CALENDAR_CREATE_REQUEST_V1')))
      throw new Error('signature');
    const r = JSON.parse(Utilities.newBlob(Utilities.base64Decode(signed.payload)).getDataAsString('UTF-8'));
    if (!jarvisKeys_(r, ['protocol','connection','nonce','issued_at','action','draft_id','document_hash','document','calendar_id']) ||
        r.protocol !== JARVIS_CREATE_PROTOCOL || r.connection !== connection ||
        r.calendar_id !== calendar ||
        !['create','get'].includes(r.action) || !/^[a-f0-9]{32}$/.test(r.nonce || '') ||
        !/^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(r.draft_id || '') ||
        !Number.isInteger(r.issued_at) || Math.abs(Date.now()/1000-r.issued_at) > 60) throw new Error('binding');
    jarvisDocument_(r.document, r.document_hash);
    const lock = LockService.getScriptLock();
    if (!lock.tryLock(1000)) throw new Error('busy');
    let event;
    try {
      const id = r.draft_id.replace(/-/g, ''), d = r.document;
      event = jarvisGoogle_(calendar, r.draft_id, 'get');
      if (!event && r.action === 'create') {
        if (+new Date(d.start) <= Date.now()) throw new Error('past');
        event = jarvisGoogle_(calendar, r.draft_id, 'create', {id,summary:d.title,description:d.note,
          start:{dateTime:d.start,timeZone:d.timezone},end:{dateTime:d.end,timeZone:d.timezone},
          attendees:[], guestsCanInviteOthers:false,guestsCanModify:false,guestsCanSeeOtherGuests:false,
          reminders:{useDefault:false,overrides:[{method:'popup',minutes:d.telegram_reminder_minutes}]},
          extendedProperties:{private:{commanderDraftId:r.draft_id,commanderDocumentHash:r.document_hash}}});
      }
      if (event) event = jarvisExact_(event, r);
    } finally { lock.releaseLock(); }
    const result = {protocol:r.protocol,connection,calendar_id:calendar,nonce:r.nonce,issued_at:Math.floor(Date.now()/1000),
      action:r.action,draft_id:r.draft_id,document_hash:r.document_hash,status:event?'FOUND':'ABSENT',event};
    const payload = Utilities.base64Encode(JSON.stringify(result), Utilities.Charset.UTF_8);
    return ContentService.createTextOutput(JSON.stringify({payload,
      signature:jarvisMac_(payload,key,'JARVIS_CALENDAR_CREATE_RESPONSE_V1')})).setMimeType(ContentService.MimeType.JSON);
  } catch (_) { return doGet(); }
}
