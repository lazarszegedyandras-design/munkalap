const NAIVE_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/
const TIMEZONE_SUFFIX_PATTERN = /(Z|[+-]\d{2}:?\d{2})$/i

function pad(value) {
  return String(value).padStart(2, '0')
}

function formatLocalDateTime(date) {
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join('-') + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * Converts an API datetime to the value expected by <input type="datetime-local">.
 *
 * Work-order timestamps are stored as local wall-clock values without a timezone.
 * Those values must be copied without passing through Date/toISOString, otherwise
 * the browser subtracts the local UTC offset every time the editor is opened.
 * Explicitly timezone-qualified inputs are converted to the browser's local time.
 */
export function toDateTimeLocalValue(value) {
  if (!value) return ''
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? '' : formatLocalDateTime(value)

  const text = String(value).trim()
  if (!text) return ''
  if (NAIVE_DATE_TIME_PATTERN.test(text) && !TIMEZONE_SUFFIX_PATTERN.test(text)) {
    return text.slice(0, 16)
  }

  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? '' : formatLocalDateTime(date)
}

export function currentDateTimeLocalValue() {
  return formatLocalDateTime(new Date())
}
