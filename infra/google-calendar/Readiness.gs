/** Owner-run read-only probe. No deployment, trigger, event write or external fetch. */
function jarvisCalendarReadiness() {
  const start = new Date();
  const end = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000);
  const calendar = CalendarApp.getDefaultCalendar();
  const events = calendar.getEvents(start, end);
  const result = {
    status: 'CALENDAR_READ_OK',
    timezone: calendar.getTimeZone(),
    interval_days: 7,
    event_count: events.length,
    events_changed: false,
    external_fetch_performed: false
  };
  console.log(JSON.stringify(result));
  return result;
}
