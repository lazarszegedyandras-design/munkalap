import assert from 'node:assert/strict'
import test from 'node:test'

process.env.TZ = 'Europe/Budapest'
const { toDateTimeLocalValue } = await import('../src/utils/datetime.js')

test('naive winter work-order time stays unchanged', () => {
  assert.equal(toDateTimeLocalValue('2026-01-15T10:30:00'), '2026-01-15T10:30')
})

test('naive summer work-order time stays unchanged', () => {
  assert.equal(toDateTimeLocalValue('2026-07-15T10:30:00'), '2026-07-15T10:30')
})

test('timezone-qualified values are converted to local time', () => {
  assert.equal(toDateTimeLocalValue('2026-01-15T09:30:00Z'), '2026-01-15T10:30')
  assert.equal(toDateTimeLocalValue('2026-07-15T08:30:00Z'), '2026-07-15T10:30')
})
