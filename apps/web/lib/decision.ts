// What the pipeline decided about an invoice and why, read from its audit trail.

import type { AuditEvent } from './types.ts'

export interface Verdict {
    model: string | null
    decision: string
    reason: string
    confidence: number
    explanation: string
}

export interface Decision {
    outcome: 'approved' | 'review'
    why: string
    flags: string[]
    verdicts: Verdict[]
    unreadable: number
}

const ENDS = new Set(['pipeline_completed', 'exception_created'])

function isVerdict(event: AuditEvent): boolean {
    return event.step === 'llm_call' && 'decision' in event.raw_output
}

/** The latest run's decision; null if the invoice has not been through the pipeline. */
export function latestDecision(events: AuditEvent[]): Decision | null {
    const end = events.filter((e) => ENDS.has(e.step)).at(-1)
    if (!end) return null
    const run = events.filter((e) => e.pipeline_run_id === end.pipeline_run_id)
    const out = end.raw_output
    return {
        outcome: out.decision === 'approved' ? 'approved' : 'review',
        // Runs recorded before the reason was kept have only a title.
        why: String(out.why ?? out.title ?? ''),
        flags: Array.isArray(out.flags) ? out.flags.map(String) : [],
        verdicts: run.filter(isVerdict).map((e) => ({
            model: e.model_id,
            decision: String(e.raw_output.decision),
            reason: String(e.raw_output.reason),
            confidence: Number(e.raw_output.confidence),
            explanation: String(e.raw_output.explanation),
        })),
        unreadable: run.filter((e) => e.step === 'llm_call' && 'unreadable' in e.raw_output).length,
    }
}

function plural(n: number, word: string): string {
    return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** One audit event, in a sentence. */
export function describe(event: AuditEvent): string {
    const out = event.raw_output
    switch (event.step) {
        case 'validation': {
            const problems = Array.isArray(out.violations) ? out.violations.length : 0
            return problems ? `The rules found ${plural(problems, 'problem')}` : 'The rules found nothing wrong'
        }
        case 'matching':
            return `Matched against the PO and receipt: ${out.summary || out.status}`
        case 'llm_call':
            if (!isVerdict(event)) return `${event.model_id} gave an unreadable answer`
            return `${event.model_id}: ${out.decision} (${out.reason}, ${Math.round(Number(out.confidence) * 100)}% sure)`
        case 'pipeline_completed':
            return 'Approved for payment'
        case 'exception_created':
            return 'Held for a person'
        case 'exception_resolved':
            return `A person chose to ${out.action}: ${out.resolution}`
        default:
            return event.step.replaceAll('_', ' ')
    }
}
