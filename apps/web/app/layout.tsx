import './globals.css'

import type { Metadata } from 'next'
import { Inter } from 'next/font/google'

import { logOut } from '@/app/actions'
import { NavLink } from '@/app/client'
import { currentUser } from '@/lib/api'
import { label } from '@/lib/format'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
    title: 'AP Reconciliation',
    description: 'Supplier invoices checked before payment: rules, then Claude, then a person',
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
    const user = await currentUser()
    return (
        <html lang="en">
            <body className={inter.className}>
                <div className="min-h-screen flex flex-col">
                    <nav className="bg-white shadow-sm border-b border-gray-200">
                        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between h-16">
                            <div className="flex">
                                <span className="flex items-center text-xl font-bold text-primary-600">AP Reconciliation</span>
                                {user && (
                                    <div className="hidden sm:ml-8 sm:flex sm:space-x-8">
                                        <NavLink href="/">Overview</NavLink>
                                        <NavLink href="/invoices">Invoices</NavLink>
                                        <NavLink href="/exceptions">Exceptions</NavLink>
                                        <NavLink href="/cost">Model spend</NavLink>
                                    </div>
                                )}
                            </div>
                            {user && (
                                <form action={logOut} className="flex items-center gap-3 text-sm text-gray-500">
                                    <span>
                                        {user.username} · {label(user.role)} · {user.tenant_name}
                                    </span>
                                    <button type="submit" className="text-primary-600 hover:text-primary-800">Log out</button>
                                </form>
                            )}
                        </div>
                    </nav>
                    <main className="flex-1">
                        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">{children}</div>
                    </main>
                </div>
            </body>
        </html>
    )
}
