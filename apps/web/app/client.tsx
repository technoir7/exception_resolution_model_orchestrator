'use client'

// The few pieces that need the browser: which page is open, and whether a
// form is still being sent.

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useFormStatus } from 'react-dom'

export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
    const path = usePathname()
    const active = href === '/' ? path === '/' : path.startsWith(href)
    return (
        <Link
            href={href}
            className={`inline-flex items-center px-1 pt-1 text-sm font-medium border-b-2 ${
                active ? 'border-primary-500 text-gray-900' : 'border-transparent text-gray-500 hover:text-gray-900'
            }`}
        >
            {children}
        </Link>
    )
}

/** A submit button that says what it is doing while the server works: a model's read or review takes seconds. */
export function Submit({ children, busy, className = 'btn-primary' }: { children: React.ReactNode; busy: string; className?: string }) {
    const { pending } = useFormStatus()
    return (
        <button type="submit" disabled={pending} className={`${className} disabled:opacity-60 disabled:cursor-wait`}>
            {pending ? busy : children}
        </button>
    )
}
