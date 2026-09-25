import test from 'node:test'
import assert from 'node:assert/strict'
import { canEditWorkOrder, formatDateTime, PHOTO_LABELS } from '../src/services/format.js'

test('lezárt vagy kész munkalap nem szerkeszthető',()=>{assert.equal(canEditWorkOrder('lezárva'),false);assert.equal(canEditWorkOrder('kész'),false);assert.equal(canEditWorkOrder('folyamatban'),true)})
test('fotók magyar kategórianevei rögzítettek',()=>{assert.equal(PHOTO_LABELS.meter,'Számláló');assert.equal(PHOTO_LABELS.damage,'Sérülés')})
test('dátumformázás hiányzó értéknél stabil',()=>{assert.equal(formatDateTime(null),'–')})
