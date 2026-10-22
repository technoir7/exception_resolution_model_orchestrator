import assert from 'node:assert/strict'
import { test } from 'node:test'

import { describe, latestDecision } from './decision.ts'
import type { AuditEvent } from './types.ts'

let sequence = 0
function event(step: string, raw_output: Record<string, unknown>, run = 'r1', extra: Partial<AuditEvent> = {}): AuditEvent {
    sequence += 1
    return {
        id: `e${sequence}`, step, sequence_number: sequence, pipeline_run_id: run, model_id: null,
        raw_input: {}, raw_output, started_at: '2026-10-22T10:00:00', completed_at: '2026-10-22T10:00:01',
        duration_ms: 5, actor_type: 'system', ...extra,
    }
}

const held = [
    event('validation', { passed: true, violations: [] }),
    event('matching', { status: 'variance', summary: 'Price above the PO' }),
    event('llm_call', { unreadable: 'not JSON' }, 'r1', { model_id: 'claude-haiku-5-5' }),
    event('llm_call', { decision: 'hold', reason: 'price', confidence: 0.9, explanation: 'Billed $12 a unit; the PO says $10.' },
        'r1', { model_id: 'claude-haiku-5-5' }),
    event('exception_created', { decision: 'review', title: 'Held: price', why: 'Billed $12 a unit; the PO says $10.',
        flags: ['Line 1 price 12 is above the PO price 10'] }),
]

test('nothing is decided before the pipeline runs', () => {
    assert.equal(latestDecision([]), null)
})

test('a hold says why, with the model that decided and what the rules flagged', () => {
    const decision = latestDecision(held)!
    assert.equal(decision.outcome, 'review')
    assert.equal(decision.why, 'Billed $12 a unit; the PO says $10.')
    assert.deepEqual(decision.flags, ['Line 1 price 12 is above the PO price 10'])
    assert.deepEqual(decision.verdicts.map((v) => [v.model, v.decision, v.reason]), [['claude-haiku-5-5', 'hold', 'price']])
    assert.equal(decision.unreadable, 1)
})

test('only the latest run counts', () => {
    const rerun = [...held,
        event('llm_call', { decision: 'pay', reason: 'none', confidence: 0.95, explanation: 'Matches.' }, 'r2',
            { model_id: 'claude-haiku-5-5' }),
        event('pipeline_completed', { decision: 'approved', why: 'Matches.', flags: [] }, 'r2')]
    const decision = latestDecision(rerun)!
    assert.equal(decision.outcome, 'approved')
    assert.equal(decision.verdicts.length, 1)
    assert.equal(decision.unreadable, 0)
})

test('a run recorded before decisions kept their reasons still reads', () => {
    const decision = latestDecision([event('exception_created', { title: 'Flagged for review' })])!
    assert.equal(decision.why, 'Flagged for review')
    assert.deepEqual(decision.flags, [])
})

test('each step reads as a sentence', () => {
    assert.equal(describe(held[0]), 'The rules found nothing wrong')
    assert.equal(describe(event('validation', { passed: false, violations: [{}, {}] })), 'The rules found 2 problems')
    assert.equal(describe(held[1]), 'Matched against the PO and receipt: Price above the PO')
    assert.equal(describe(held[2]), 'claude-haiku-5-5 gave an unreadable answer')
    assert.equal(describe(held[3]), 'claude-haiku-5-5: hold (price, 90% sure)')
    assert.equal(describe(held[4]), 'Held for a person')
    assert.equal(describe(event('pipeline_completed', { decision: 'approved', why: 'x' })), 'Approved for payment')
    assert.equal(describe(event('exception_resolved', { action: 'approve', resolution: 'Called the vendor' })),
        'A person chose to approve: Called the vendor')
})
