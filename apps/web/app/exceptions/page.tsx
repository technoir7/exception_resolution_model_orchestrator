import Link from 'next/link'

interface Exception {
    id: string
    invoice_id: string
    invoice_number: string
    category: string
    severity: string
    status: string
    title: string
    sla_deadline: string
    sla_breached: boolean
    created_at: string
}

async function getExceptions(): Promise<Exception[]> {
    return [
        {
            id: '1',
            invoice_id: '3',
            invoice_number: 'INV-2024-003',
            category: 'missing_po',
            severity: 'high',
            status: 'open',
            title: 'PO PO-MISSING-999 not found',
            sla_deadline: '2024-01-19 18:00',
            sla_breached: false,
            created_at: '2024-01-18 10:00',
        },
        {
            id: '2',
            invoice_id: '4',
            invoice_number: 'INV-2024-004',
            category: 'duplicate',
            severity: 'high',
            status: 'open',
            title: 'Exact duplicate of INV-2024-001',
            sla_deadline: '2024-01-15 14:00',
            sla_breached: true,
            created_at: '2024-01-15 10:00',
        },
        {
            id: '3',
            invoice_id: '5',
            invoice_number: 'INV-2024-005',
            category: 'amount_variance',
            severity: 'high',
            status: 'open',
            title: 'Amount variance 20% exceeds tolerance',
            sla_deadline: '2024-01-21 08:00',
            sla_breached: false,
            created_at: '2024-01-20 12:00',
        },
        {
            id: '4',
            invoice_id: '9',
            invoice_number: 'INV-2024-009',
            category: 'vendor_mismatch',
            severity: 'low',
            status: 'open',
            title: 'Vendor V999 does not match PO vendor V001',
            sla_deadline: '2024-01-23 10:00',
            sla_breached: false,
            created_at: '2024-01-21 10:00',
        },
    ]
}

function getSeverityClass(severity: string): string {
    return `severity-${severity}`
}

export default async function ExceptionsPage() {
    const exceptions = await getExceptions()

    return (
        <div>
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Exception Queue</h1>
                    <p className="text-gray-500">{exceptions.length} open exceptions</p>
                </div>
                <div className="flex gap-2">
                    <select className="border border-gray-300 rounded-md px-3 py-2 text-sm">
                        <option value="">All Categories</option>
                        <option value="missing_po">Missing PO</option>
                        <option value="duplicate">Duplicate</option>
                        <option value="amount_variance">Amount Variance</option>
                        <option value="vendor_mismatch">Vendor Mismatch</option>
                    </select>
                    <select className="border border-gray-300 rounded-md px-3 py-2 text-sm">
                        <option value="">All Severities</option>
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                        <option value="critical">Critical</option>
                    </select>
                </div>
            </div>

            <div className="space-y-4">
                {exceptions.map((exc) => (
                    <div key={exc.id} className={`card ${exc.sla_breached ? 'border-red-300 bg-red-50' : ''}`}>
                        <div className="flex justify-between items-start">
                            <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                    <Link href={`/exceptions/${exc.id}`} className="text-lg font-medium text-gray-900 hover:text-primary-600">
                                        {exc.title}
                                    </Link>
                                    <span className={`status-badge ${getSeverityClass(exc.severity)}`}>
                                        {exc.severity}
                                    </span>
                                    {exc.sla_breached && (
                                        <span className="status-badge bg-red-600 text-white">
                                            SLA Breached
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-center gap-4 text-sm text-gray-500">
                                    <Link href={`/invoices/${exc.invoice_id}`} className="hover:text-primary-600">
                                        {exc.invoice_number}
                                    </Link>
                                    <span>•</span>
                                    <span className="capitalize">{exc.category.replace('_', ' ')}</span>
                                    <span>•</span>
                                    <span>Created {exc.created_at}</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-sm text-gray-500">SLA Deadline</p>
                                <p className={`text-sm font-medium ${exc.sla_breached ? 'text-red-600' : 'text-gray-900'}`}>
                                    {exc.sla_deadline}
                                </p>
                            </div>
                        </div>
                        <div className="mt-4 flex gap-2">
                            <Link href={`/exceptions/${exc.id}`} className="btn-primary text-sm">
                                Review
                            </Link>
                            <button className="btn-secondary text-sm">
                                Assign to Me
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}
