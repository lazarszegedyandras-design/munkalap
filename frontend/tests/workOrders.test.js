import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { assetMachineLabel, assetMachineType, supplierWorksheetEmail, supplierWorksheetPhone, workOrderAssetSummary } from '../src/utils/workOrders.js'

test('géptípus és gyári szám formázása', () => {
  const asset = { manufacturer: 'Ricoh', model: 'SP 8300DN', serial_number: 'TEST-SERIAL-208' }
  assert.equal(assetMachineType(asset), 'Ricoh / SP 8300DN')
  assert.equal(assetMachineLabel(asset), 'Ricoh / SP 8300DN · gyári szám: TEST-SERIAL-208')
})

test('munkalap több kapcsolt gépének összefoglalása', () => {
  assert.equal(workOrderAssetSummary({ assets: [
    { manufacturer: 'Ricoh', model: 'SP 8300DN', serial_number: 'A1' },
    { manufacturer: 'Canon', type: 'MFP', serial_number: 'B2' },
  ] }), 'Ricoh / SP 8300DN · gyári szám: A1; Canon / MFP · gyári szám: B2')
})

test('a nyomtatási szolgáltatási elérhetőség elsőbbséget élvez', () => {
  const supplier = {
    phone: '+36 1 111 1111',
    mobile_phone: '+36 20 222 2222',
    email: 'info@example.com',
    worksheet_phone: '+36 1 333 3333 / +36 20 444 4444',
    worksheet_email: 'helpdesk@example.com',
  }
  assert.equal(supplierWorksheetPhone(supplier), '+36 1 333 3333 / +36 20 444 4444')
  assert.equal(supplierWorksheetEmail(supplier), 'helpdesk@example.com')
})

test('régi cégprofilnál a vezetékes telefon megelőzi a mobiltelefont', () => {
  const supplier = { phone: '+36 1 111 1111', mobile_phone: '+36 20 222 2222', email: 'info@example.com' }
  assert.equal(supplierWorksheetPhone(supplier), '+36 1 111 1111')
  assert.equal(supplierWorksheetEmail(supplier), 'info@example.com')
})


test('nyomtatott munkalap biztonságos A4 margót, nagyobb fejlécet és kompakt munkaterületet használ', () => {
  const css = readFileSync(new URL('../src/styles/app.css', import.meta.url), 'utf8')
  assert.match(css, /@page\s*\{\s*size:\s*A4;\s*margin:\s*12mm;/)
  assert.match(css, /html, body\s*\{\s*margin:\s*0;\s*padding:\s*0;/)
  assert.match(css, /\.print-sheet\.worksheet-print\s*\{[\s\S]*?min-height:\s*273mm;[\s\S]*?display:\s*flex\s*!important;/)
  assert.match(css, /\.worksheet-title h1\s*\{[^}]*font-size:\s*22px;/)
  assert.match(css, /\.party-name\s*\{[^}]*font-size:\s*13px;/)
  assert.match(css, /\.worksheet-block--work-done\s*\{[^}]*flex:\s*0\s+0\s+auto;[^}]*min-height:\s*56mm;/)
  assert.match(css, /\.worksheet-signatures\s*\{[^}]*margin-top:\s*auto;/)
  assert.match(css, /\.worksheet-title\s*\{[^}]*border-bottom-width:\s*4px;/)
  assert.match(css, /\.worksheet-number\s*\{[^}]*border-width:\s*2px;/)
  assert.match(css, /\.worksheet-meta th,[\s\S]*?border-width:\s*2px;/)
  assert.match(css, /\.worksheet-signatures div\s*\{[^}]*border-top-width:\s*2px;/)
})



test('nyomtatott munkalap alsó adatterülete nagyobb betűt és normál súlyú meta mezőneveket használ', () => {
  const css = readFileSync(new URL('../src/styles/app.css', import.meta.url), 'utf8')
  assert.match(css, /\.worksheet-print\s*\{[^}]*font-size:\s*11px;/)
  assert.match(css, /\.worksheet-meta\s*\{[^}]*font-size:\s*11px;/)
  assert.match(css, /\.worksheet-meta th\s*\{[^}]*font-weight:\s*400;/)
  assert.match(css, /\.worksheet-table\s*\{[^}]*font-size:\s*9\.6px;/)
  assert.match(css, /\.worksheet-block--work-done\s*\{[^}]*min-height:\s*56mm;/)
  assert.match(css, /\.worksheet-block--final-status\s*\{[^}]*min-height:\s*24mm;/)
  assert.match(css, /\.worksheet-block--final-status p\s*\{[^}]*min-height:\s*17mm;/)
})

test('nyomtatott kapcsolódó eszközök táblában karbantartási dátum váltja az állapotot és cégkódot', () => {
  const source = readFileSync(new URL('../src/pages/WorkOrders.jsx', import.meta.url), 'utf8')
  const tableStart = source.indexOf('<h3>Kapcsolódó eszközök</h3>')
  const tableEnd = source.indexOf('<div className="worksheet-block worksheet-block--double">', tableStart)
  const printableAssetTable = source.slice(tableStart, tableEnd)
  assert.match(printableAssetTable, /<th>Utolsó karbantartás<\/th>/)
  assert.match(printableAssetTable, /formatPrintDateOnly\(asset\.last_maintenance_date\)/)
  assert.doesNotMatch(printableAssetTable, /<th>Állapot<\/th>/)
  assert.doesNotMatch(printableAssetTable, /<th>Cégkód<\/th>/)
  assert.match(printableAssetTable, /colSpan="6"/)
})

test('nyomtatott munkalap üres mezőket nem kötőjellel, hanem üresen jelenít meg', () => {
  const source = readFileSync(new URL('../src/pages/WorkOrders.jsx', import.meta.url), 'utf8')
  assert.match(source, /function printValue\(input\) \{[\s\S]*?\? '' : input/)
  assert.match(source, /<strong>E-mail:<\/strong> \{printValue\(order\.customer_email\)\}/)
  assert.match(source, /<h3 className="worksheet-block-label">Elvégzett munka<\/h3>[\s\S]*?<div className="worksheet-block worksheet-block--work-done"><p>\{printValue\(order\.work_done\)\}<\/p><\/div>/)
  assert.match(source, /<h3 className="worksheet-block-label">Végállapot<\/h3>[\s\S]*?<div className="worksheet-block worksheet-block--final-status"><p>\{printValue\(order\.final_status\)\}<\/p><\/div>/)
})

test('nyomtatott munkalapon a tervezett nap és a szerződés típusa után külön sorban vannak a tényleges időpontok', () => {
  const source = readFileSync(new URL('../src/pages/WorkOrders.jsx', import.meta.url), 'utf8')
  const workTimeIndex = source.indexOf('<th>Munkaidő</th>')
  const plannedIndex = source.indexOf('<th>Tervezett nap</th>', workTimeIndex)
  const startedIndex = source.indexOf('<th>Tényleges kezdés</th>', plannedIndex)
  const completedIndex = source.indexOf('<th>Tényleges befejezés</th>', startedIndex)
  assert.ok(workTimeIndex >= 0 && plannedIndex > workTimeIndex && startedIndex > plannedIndex && completedIndex > startedIndex)
  assert.match(source, /<th>Tervezett nap<\/th><td>\{formatPrintDateOnly\(order\.planned_date\)\}<\/td><th>Szerződés típusa<\/th><td>\{printValue\(order\.contract_type\)\}<\/td>/)
  assert.match(source, /<tr><th>Tényleges kezdés<\/th><td colSpan="3">\{formatPrintDate\(order\.started_at\)\}<\/td><\/tr>/)
  assert.match(source, /<tr><th>Tényleges befejezés<\/th><td colSpan="3">\{formatPrintDate\(order\.completed_at\)\}<\/td><\/tr>/)
  assert.match(source, /<Field label="Szerződés típusa"><input maxLength="120"/)
})

test('a hiba, elvégzett munka és végállapot feliratok a keret fölött vannak', () => {
  const source = readFileSync(new URL('../src/pages/WorkOrders.jsx', import.meta.url), 'utf8')
  assert.match(source, /<h3 className="worksheet-block-label">Hiba \/ feladat leírása<\/h3>\s*<div className="worksheet-block worksheet-block--double"><p>/)
  assert.match(source, /<h3 className="worksheet-block-label">Elvégzett munka<\/h3>\s*<div className="worksheet-block worksheet-block--work-done"><p>/)
  assert.match(source, /<h3 className="worksheet-block-label">Végállapot<\/h3>\s*<div className="worksheet-block worksheet-block--final-status"><p>/)
})
