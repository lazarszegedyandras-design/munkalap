import test from 'node:test'
import assert from 'node:assert/strict'
import { workOrderIdFromData } from '../src/services/pushData.js'

test('work-order push data resolves a deep-link id', () => {
  assert.equal(workOrderIdFromData({ source_type: 'work_order', source_id: '42' }), 42)
})

test('non work-order or invalid ids are ignored', () => {
  assert.equal(workOrderIdFromData({ source_type: 'crm_activity', source_id: '42' }), null)
  assert.equal(workOrderIdFromData({ source_type: 'work_order', source_id: 'x' }), null)
})
