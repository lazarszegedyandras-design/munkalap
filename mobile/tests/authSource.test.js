import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const source=fs.readFileSync(new URL('../src/services/auth.js',import.meta.url),'utf8')
test('auth nem ír localStorage-ba',()=>{assert.equal(source.includes('localStorage.setItem'),false);assert.equal(source.includes('localStorage.getItem'),false)})
test('natív refresh token secure storage-ban van',()=>{assert.match(source,/SecureStorage\.set\(/);assert.match(source,/SecureStorage\.remove\(/);assert.match(source,/Capacitor\.isNativePlatform\(\)/)})
