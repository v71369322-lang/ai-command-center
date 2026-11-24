/** Read-only server bridge. Provision properties and approve deployment separately. */
const JARVIS_PROTOCOL = 'jarvis-agenda-v1';

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

function doGet() {
  return ContentService.createTextOutput('{"error":"unavailable"}')
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    if (!e || !e.postData || e.postData.type !== 'application/json' ||
        typeof e.postData.contents !== 'string' || e.postData.contents.length > 4096 ||
        (e.queryString && e.queryString.length)) throw new Error('request');
    const properties = PropertiesService.getScriptProperties();
    const key = properties.getProperty('JARVIS_HMAC_KEY');
    const connection = properties.getProperty('JARVIS_CONNECTION');
    if (!/^[a-f0-9]{64}$/.test(key || '') || !/^[a-f0-9]{64}$/.test(connection || '')) {
      throw new Error('configuration');
    }
    const envelope = JSON.parse(e.postData.contents);
    if (Object.keys(envelope).sort().join(',') !== 'payload,signature' ||
        typeof envelope.payload !== 'string' || envelope.payload.length > 3000 ||
        !/^[a-f0-9]{64}$/.test(envelope.signature || '') ||
        !jarvisEqual_(envelope.signature, jarvisMac_(envelope.payload, key, 'JARVIS_CALENDAR_REQUEST_V1'))) {
      throw new Error('signature');
    }
    const request = JSON.parse(Utilities.newBlob(Utilities.base64Decode(envelope.payload)).getDataAsString('UTF-8'));
    if (Object.keys(request).sort().join(',') !== 'connection,end,issued_at,nonce,protocol,start' ||
        request.protocol !== JARVIS_PROTOCOL || request.connection !== connection ||
        typeof request.nonce !== 'string' || !/^[a-f0-9]{32}$/.test(request.nonce) || !Number.isInteger(request.issued_at) ||
        Math.abs(Date.now() / 1000 - request.issued_at) > 60) throw new Error('binding');
    const iso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;
    if (typeof request.start !== 'string' || typeof request.end !== 'string' ||
        !iso.test(request.start) || !iso.test(request.end)) throw new Error('interval');
    const start = new Date(request.start), end = new Date(request.end);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) ||
        end <= start || end - start > 7 * 86400000) throw new Error('interval');
    // Best-effort duplicate suppression only: CacheService can evict entries.
    // Freshness plus the response nonce binding are the cryptographic controls.
    const lock = LockService.getScriptLock();
    if (!lock.tryLock(1000)) throw new Error('busy');
    try {
      const cache = CacheService.getScriptCache();
      if (cache.get(request.nonce)) throw new Error('duplicate');
      cache.put(request.nonce, 'seen', 120);
    } finally { lock.releaseLock(); }
    const calendar = CalendarApp.getDefaultCalendar();
    if (calendar.getTimeZone() !== 'Europe/Moscow') throw new Error('timezone');
    const found = calendar.getEvents(start, end, {max: 51});
    const events = found.slice(0, 50).map(event => {
      function instant(date) {
        return event.isAllDayEvent()
          ? {date: Utilities.formatDate(date, 'Europe/Moscow', 'yyyy-MM-dd')}
          : {dateTime: date.toISOString()};
      }
      return {summary: Array.from(event.getTitle().replace(/\s+/g, ' ').trim()).slice(0, 120).join(''),
        start: instant(event.getStartTime()), end: instant(event.getEndTime())};
    });
    const result = {protocol: JARVIS_PROTOCOL, connection, nonce: request.nonce,
      issued_at: Math.floor(Date.now() / 1000), start: request.start, end: request.end,
      timezone: 'Europe/Moscow', events, truncated: found.length > 50};
    const payload = Utilities.base64Encode(JSON.stringify(result), Utilities.Charset.UTF_8);
    return ContentService.createTextOutput(JSON.stringify({payload,
      signature: jarvisMac_(payload, key, 'JARVIS_CALENDAR_RESPONSE_V1')}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (_) {
    // No provider exceptions, identifiers, event contents, keys or tokens in logs.
    return doGet();
  }
}
