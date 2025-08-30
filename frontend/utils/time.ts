// Frontend time utilities: parse and format in the user's timezone/locale

export const userLocale: string = (typeof navigator !== 'undefined' && navigator.language) || 'en-US';

export function parseDate(input: string | number | Date): Date {
  if (input instanceof Date) return input;
  if (typeof input === 'number') {
    // Heuristic: treat < 1e12 as seconds and >= 1e12 as milliseconds
    const ms = input < 1e12 ? input * 1000 : input;
    return new Date(ms);
  }
  // ISO strings parse as UTC then render in local when formatted with toLocale*
  return new Date(input);
}

export function formatDateTimeLocal(
  input: string | number | Date,
  options: Intl.DateTimeFormatOptions = {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }
): string {
  return parseDate(input).toLocaleString(userLocale, options);
}

export function formatTimeLocal(
  input: string | number | Date,
  options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hour12: false }
): string {
  return parseDate(input).toLocaleTimeString(userLocale, options);
}

export function formatDateLocal(
  input: string | number | Date,
  options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: 'numeric' }
): string {
  return parseDate(input).toLocaleDateString(userLocale, options);
}

export function relativeTimeFromNow(input: string | number | Date): string {
  const d = parseDate(input);
  const diffMs = Date.now() - d.getTime();
  const rtf = new Intl.RelativeTimeFormat(userLocale, { numeric: 'auto' });
  const abs = Math.abs(diffMs);
  const minutes = Math.round(abs / 60000);
  const hours = Math.round(abs / 3600000);
  const days = Math.round(abs / 86400000);
  if (abs < 60000) return rtf.format(Math.round(diffMs / 1000), 'second');
  if (abs < 3600000) return rtf.format(Math.sign(diffMs) * minutes, 'minute');
  if (abs < 86400000) return rtf.format(Math.sign(diffMs) * hours, 'hour');
  return rtf.format(Math.sign(diffMs) * days, 'day');
}

