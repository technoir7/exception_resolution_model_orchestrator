import Link from 'next/link'

// Types for dashboard data
interface DashboardStats {
    totalInvoices: number
    touchlessCount: number
    exceptionCount: number
    touchlessRate: number
    avgCostPerInvoice: string
    openExceptions: number
    slaBreached: number
}

async function getDashboardStats(): Promise<DashboardStats> {
    // In production, fetch from API
    // For demo, return mock data
    return {
        totalInvoices: 10,
        touchlessCount: 6,
        exceptionCount: 4,
        touchlessRate: 60,
        avgCostPerInvoice: '$0.023',
        openExceptions: 4,
        slaBreached: 0,
    }
}

export default async function DashboardPage() {
    const stats = await getDashboardStats()

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h1>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
                <div className="card">
                    <dt className="text-sm font-medium text-gray-500 truncate">Total Invoices</dt>
                    <dd className="mt-1 text-3xl font-semibold text-gray-900">{stats.totalInvoices}</dd>
                </div>

                <div className="card">
                    <dt className="text-sm font-medium text-gray-500 truncate">Touchless Rate</dt>
                    <dd className="mt-1 text-3xl font-semibold text-green-600">{stats.touchlessRate}%</dd>
                    <p className="text-sm text-gray-500">{stats.touchlessCount} of {stats.totalInvoices}</p>
                </div>

                <div className="card">
                    <dt className="text-sm font-medium text-gray-500 truncate">Open Exceptions</dt>
                    <dd className="mt-1 text-3xl font-semibold text-orange-600">{stats.openExceptions}</dd>
                    {stats.slaBreached > 0 && (
                        <p className="text-sm text-red-600">{stats.slaBreached} SLA breached</p>
                    )}
                </div>

                <div className="card">
                    <dt className="text-sm font-medium text-gray-500 truncate">Avg Cost/Invoice</dt>
                    <dd className="mt-1 text-3xl font-semibold text-gray-900">{stats.avgCostPerInvoice}</dd>
                </div>
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <div className="card">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Quick Actions</h2>
                    <div className="space-y-3">
                        <Link href="/invoices" className="btn-primary block text-center">
                            View All Invoices
                        </Link>
                        <Link href="/exceptions" className="btn-secondary block text-center">
                            Review Exception Queue
                        </Link>
                        <Link href="/cost" className="btn-secondary block text-center">
                            View Cost Dashboard
                        </Link>
                    </div>
                </div>

                <div className="card">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">System Status</h2>
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-500">API</span>
                            <span className="status-badge status-approved">Healthy</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-500">Database</span>
                            <span className="status-badge status-approved">Connected</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-500">Celery Worker</span>
                            <span className="status-badge status-approved">Running</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-500">LLM Provider</span>
                            <span className="status-badge status-processing">Mock (Demo)</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
