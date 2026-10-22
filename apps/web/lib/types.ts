// The API's responses, as the dashboard reads them (apps/api/schemas).
// Amounts arrive as strings, so no money passes through a float.

export type InvoiceStatus = 'pending' | 'processing' | 'matched' | 'exception' | 'approved' | 'rejected'

export interface Page<T> {
    items: T[]
    total: number
    page: number
    page_size: number
    pages: number
}

export interface LineItem {
    line_number: number
    description: string
    quantity: string
    unit_price: string
    amount: string
}

export interface Invoice {
    id: string
    status: InvoiceStatus
    document_type: string
    original_filename: string | null
    invoice_number: string | null
    invoice_date: string | null
    due_date: string | null
    vendor_id: string | null
    vendor_name: string | null
    po_number: string | null
    currency: string
    subtotal: string | null
    tax_amount: string | null
    total_amount: string | null
    line_items: LineItem[] | null
    extracted_data: {
        remit_to?: { bank: string; account_last4: string }
        notes?: string
        service_period?: string
        read_by?: string
    } | null
    created_at: string
}

export interface InvoiceSummary {
    id: string
    invoice_number: string | null
    vendor_name: string | null
    total_amount: string | null
    status: InvoiceStatus
    created_at: string
}

export interface Exception {
    id: string
    invoice_id: string
    invoice: InvoiceSummary | null
    category: string
    severity: string
    status: 'open' | 'in_progress' | 'resolved' | 'escalated' | 'rejected'
    owner_role: string
    title: string
    description: string | null
    details: { flags?: string[] } | null
    sla_deadline: string
    resolution: string | null
    resolution_action: string | null
    resolved_at: string | null
    created_at: string
}

export interface ExceptionPage extends Page<Exception> {
    open_count: number
}

export interface AuditEvent {
    id: string
    step: string
    sequence_number: number
    pipeline_run_id: string
    model_id: string | null
    raw_input: Record<string, unknown>
    raw_output: Record<string, unknown>
    started_at: string
    completed_at: string
    duration_ms: number
    actor_type: string
}

export interface AuditTimeline {
    events: AuditEvent[]
}

export interface ModelSpend {
    model_id: string | null
    calls: number
    input_tokens: number
    output_tokens: number
    cost_usd: string
}

export interface CostSummary {
    start_date: string
    end_date: string
    total_cost_usd: string
    invoices_by_status: Partial<Record<InvoiceStatus, number>>
    cost_per_invoice: string
    spent_today: string
    daily_cap_usd: string
    by_model: ModelSpend[]
}

export interface InvoiceCost {
    total_cost_usd: string
    calls: { model_id: string | null; input_tokens: number; output_tokens: number; cost_usd: string; at: string }[]
}

export interface User {
    username: string
    role: string
    tenant_name: string
}
