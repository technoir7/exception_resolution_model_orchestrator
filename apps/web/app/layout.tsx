import './globals.css'
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import Link from 'next/link'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
    title: 'AP Reconciliation Orchestrator',
    description: 'Cost per verified invoice + audit replay',
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="en">
            <body className={inter.className}>
                <div className="min-h-screen flex flex-col">
                    {/* Navigation */}
                    <nav className="bg-white shadow-sm border-b border-gray-200">
                        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                            <div className="flex justify-between h-16">
                                <div className="flex">
                                    <div className="flex-shrink-0 flex items-center">
                                        <span className="text-xl font-bold text-primary-600">AP Reconciliation</span>
                                    </div>
                                    <div className="hidden sm:ml-8 sm:flex sm:space-x-8">
                                        <Link
                                            href="/"
                                            className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-900 border-b-2 border-transparent hover:border-primary-500"
                                        >
                                            Dashboard
                                        </Link>
                                        <Link
                                            href="/invoices"
                                            className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-500 border-b-2 border-transparent hover:border-primary-500 hover:text-gray-900"
                                        >
                                            Invoices
                                        </Link>
                                        <Link
                                            href="/exceptions"
                                            className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-500 border-b-2 border-transparent hover:border-primary-500 hover:text-gray-900"
                                        >
                                            Exceptions
                                        </Link>
                                        <Link
                                            href="/cost"
                                            className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-500 border-b-2 border-transparent hover:border-primary-500 hover:text-gray-900"
                                        >
                                            Cost Dashboard
                                        </Link>
                                    </div>
                                </div>
                                <div className="flex items-center">
                                    <span className="text-sm text-gray-500">Demo User</span>
                                </div>
                            </div>
                        </div>
                    </nav>

                    {/* Main content */}
                    <main className="flex-1">
                        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
                            {children}
                        </div>
                    </main>

                    {/* Footer */}
                    <footer className="bg-white border-t border-gray-200">
                        <div className="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8">
                            <p className="text-center text-sm text-gray-500">
                                AP Reconciliation Orchestrator MVP
                            </p>
                        </div>
                    </footer>
                </div>
            </body>
        </html>
    )
}
