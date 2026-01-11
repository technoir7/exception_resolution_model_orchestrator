/**
 * API client for the AP Reconciliation API.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface ApiError {
    detail: string
}

async function fetchApi<T>(
    endpoint: string,
    options?: RequestInit
): Promise<T> {
    const url = `${API_URL}${endpoint}`

    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options?.headers,
        },
    })

    if (!response.ok) {
        const error = await response.json() as ApiError
        throw new Error(error.detail || 'API request failed')
    }

    return response.json()
}

// Invoice API
export interface Invoice {
    id: string
    invoice_number: string
    vendor_name: string
    vendor_id: string
    total_amount: string
    status: string
    created_at: string
}

export interface InvoiceListResponse {
    items: Invoice[]
    total: number
    page: number
    page_size: number
    pages: number
}

export async function getInvoices(page = 1, status?: string): Promise<InvoiceListResponse> {
    let url = `/invoices?page=${page}`
    if (status) url += `&status=${status}`
    return fetchApi<InvoiceListResponse>(url)
}

export async function getInvoice(id: string): Promise<Invoice> {
    return fetchApi<Invoice>(`/invoices/${id}`)
}

// Exception API
export interface Exception {
    id: string
    invoice_id: string
    category: string
    severity: string
    status: string
    title: string
    description: string
    sla_deadline: string
    sla_breached: boolean
    created_at: string
}

export interface ExceptionListResponse {
    items: Exception[]
    total: number
    page: number
    page_size: number
    pages: number
    open_count: number
    sla_breached_count: number
}

export async function getExceptions(page = 1): Promise<ExceptionListResponse> {
    return fetchApi<ExceptionListResponse>(`/exceptions?page=${page}`)
}

export async function getException(id: string): Promise<Exception> {
    return fetchApi<Exception>(`/exceptions/${id}`)
}

export async function resolveException(
    id: string,
    resolution: string,
    action: string
): Promise<Exception> {
    return fetchApi<Exception>(`/exceptions/${id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({
            resolution,
            resolution_action: action,
        }),
    })
}

// Cost API
export interface CostDashboard {
    total_cost_usd: string
    total_invoices_processed: number
    avg_cost_per_invoice: string
    avg_cost_per_verified_invoice: string
    touchless_count: number
    exception_count: number
    touchless_rate: number
    cache_metrics: {
        total_requests: number
        cache_hits: number
        cache_misses: number
        hit_rate: number
    }
}

export async function getCostDashboard(): Promise<CostDashboard> {
    return fetchApi<CostDashboard>('/metrics/cost')
}

// Pipeline API
export async function runPipeline(invoiceId: string): Promise<any> {
    return fetchApi(`/pipeline/run/${invoiceId}`, {
        method: 'POST',
    })
}

// Auth API
export interface LoginResponse {
    access_token: string
    token_type: string
    expires_in: number
}

export async function login(username: string, password: string): Promise<LoginResponse> {
    return fetchApi<LoginResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
    })
}
