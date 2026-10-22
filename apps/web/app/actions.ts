'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { ApiError, api, logInToApi, TOKEN_COOKIE } from '@/lib/api'
import type { Invoice, Page } from '@/lib/types'

export async function logIn(form: FormData) {
    const login = await logInToApi(String(form.get('username')), String(form.get('password')))
    if (!login) redirect('/login?failed=1')
    const jar = await cookies()
    jar.set(TOKEN_COOKIE, login.access_token, {
        httpOnly: true,
        sameSite: 'lax',
        secure: process.env.NODE_ENV === 'production',
        maxAge: login.expires_in,
        path: '/',
    })
    redirect('/')
}

export async function logOut() {
    const jar = await cookies()
    jar.delete(TOKEN_COOKIE)
    redirect('/login')
}

function withError(path: string, error: unknown): never {
    if (error instanceof ApiError) redirect(`${path}?error=${encodeURIComponent(error.message)}`)
    throw error
}

export async function uploadPdf(form: FormData) {
    const file = form.get('pdf')
    if (!(file instanceof File) || file.size === 0) redirect('/invoices?error=Choose+a+PDF+first.')
    let invoice: Invoice
    try {
        invoice = await api<Invoice>(`/ingest/invoice-pdf?filename=${encodeURIComponent(file.name)}`, {
            method: 'POST',
            body: await file.arrayBuffer(),
            contentType: 'application/pdf',
        })
    } catch (error) {
        withError('/invoices', error)
    }
    redirect(`/invoices/${invoice.id}`)
}

export async function processInvoice(id: string) {
    try {
        await api(`/pipeline/run/${id}`, { method: 'POST' })
    } catch (error) {
        withError(`/invoices/${id}`, error)
    }
    redirect(`/invoices/${id}`)
}

export async function processPending() {
    // The API takes up to 100 at a time; a larger backlog takes another click.
    const pending = await api<Page<Invoice>>('/invoices?status=pending&page_size=100')
    if (pending.items.length) {
        try {
            await api('/pipeline/run_batch', { method: 'POST', json: { invoice_ids: pending.items.map((i) => i.id) } })
        } catch (error) {
            withError('/invoices', error)
        }
    }
    redirect('/invoices')
}

export async function resolveException(id: string, form: FormData) {
    try {
        await api(`/exceptions/${id}/resolve`, {
            method: 'POST',
            json: { resolution_action: form.get('action'), resolution: form.get('resolution') },
        })
    } catch (error) {
        withError(`/exceptions/${id}`, error)
    }
    redirect(`/exceptions/${id}`)
}
