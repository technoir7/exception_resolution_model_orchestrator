// The API, called from the server with the logged-in user's token. The token
// lives in an httpOnly cookie, so the browser's scripts never see it.

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import type { User } from './types'

export const API_URL = process.env.API_URL ?? 'http://localhost:8000'
export const TOKEN_COOKIE = 'token'

export class ApiError extends Error {
    constructor(public status: number, message: string) {
        super(message)
    }
}

type Options = { method?: string; json?: unknown; body?: BodyInit; contentType?: string }

async function send(path: string, options: Options, token?: string): Promise<Response> {
    const headers: Record<string, string> = {}
    if (token) headers.Authorization = `Bearer ${token}`
    if (options.json !== undefined) headers['Content-Type'] = 'application/json'
    if (options.contentType) headers['Content-Type'] = options.contentType
    try {
        return await fetch(`${API_URL}${path}`, {
            method: options.method ?? 'GET',
            headers,
            body: options.json !== undefined ? JSON.stringify(options.json) : options.body,
            cache: 'no-store',
        })
    } catch (error) {
        throw new Error(`The API at ${API_URL} could not be reached`, { cause: error })
    }
}

async function detail(response: Response): Promise<string> {
    const text = await response.text()
    try {
        const body = JSON.parse(text)
        return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
        return text || response.statusText
    }
}

/** Sends a logged-in request; a missing or expired login goes to /login. */
export async function api<T>(path: string, options: Options = {}): Promise<T> {
    const token = (await cookies()).get(TOKEN_COOKIE)?.value
    if (!token) redirect('/login')
    const response = await send(path, options, token)
    if (response.status === 401) redirect('/login')
    if (!response.ok) throw new ApiError(response.status, await detail(response))
    return response.json()
}

export async function logInToApi(username: string, password: string) {
    const response = await send('/auth/login', { method: 'POST', json: { username, password } })
    if (!response.ok) return null
    return (await response.json()) as { access_token: string; expires_in: number }
}

/** Who is logged in, or null: unlike `api`, never redirects, as the login page itself asks. */
export async function currentUser(): Promise<User | null> {
    const token = (await cookies()).get(TOKEN_COOKIE)?.value
    if (!token) return null
    let response: Response
    try {
        response = await send('/auth/me', {}, token)
    } catch {
        // The page itself calls the API next and reports it unreachable;
        // the layout around it should still render.
        return null
    }
    return response.ok ? response.json() : null
}
