import assert from 'node:assert/strict'
import { test } from 'node:test'

import { cost, day, instant, label, money, overdue } from './format.ts'

test('money is written as an invoice prints it', () => {
    assert.equal(money('1430.62'), '$1,430.62')
    assert.equal(money('100', 'EUR'), '€100.00')
    assert.equal(money(null), '—')
})

test('a model cost of a fraction of a cent keeps its digits', () => {
    assert.equal(cost('0.00111'), '$0.00111')
    assert.equal(cost('0.023'), '$0.023')
    assert.equal(cost('1.23456'), '$1.23')
    assert.equal(cost('0'), '$0.00')
})

test('a time without a zone is UTC, as the API stores it', () => {
    assert.equal(instant('2026-10-22T22:51:41').toISOString(), '2026-10-22T22:51:41.000Z')
    assert.equal(instant('2026-10-22T22:51:41+00:00').toISOString(), '2026-10-22T22:51:41.000Z')
})

test('a date is the day printed, wherever the server is', () => {
    assert.equal(day('2026-02-20'), 'Feb 20, 2026')
    assert.equal(day(null), '—')
})

test('codes read as words', () => {
    assert.equal(label('amount_variance'), 'Amount variance')
    assert.equal(label('ap_manager'), 'AP manager')
})

test('an exception is overdue past its deadline', () => {
    const now = new Date('2026-10-22T12:00:00Z')
    assert.equal(overdue('2026-10-22T11:59:00', now), true)
    assert.equal(overdue('2026-10-22T12:01:00', now), false)
})
