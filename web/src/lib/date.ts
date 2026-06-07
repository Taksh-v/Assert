/**
 * Safely parses an ISO-8601 datetime string, ensuring naive UTC strings 
 * (lacking 'Z' or offset) are treated as UTC instead of local time.
 */
export function parseUTCDate(isoString?: string): Date {
  if (!isoString) return new Date(NaN);
  let normalized = isoString.trim();
  const hasTimezone = /[zZ]$|[\+\-]\d{2}:?\d{2}$/.test(normalized);
  if (!hasTimezone) {
    normalized += "Z";
  }
  return new Date(normalized);
}
