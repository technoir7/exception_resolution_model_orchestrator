import Link from 'next/link'

interface ExceptionDetail {
    id: string
    invoice_id: string
    invoice_number: string
    category: string
    severity: string
    status: string
    title: string
    description: string
    details: Record<string, any>
    owner_role: string
    sla_deadline: string
    sla_breached: boolean
    created_at: string
}

async function getException(id: string): Promise<ExceptionDetail> {
    return {
        id,
        invoice_id: '3',
        invoice_number: 'INV-2024-003',
        category: 'missing_po',
        severity: 'high',
        status: 'open',
        title: 'PO PO-MISSING-999 not found',
        description: 'The referenced purchase order PO-MISSING-999 does not exist in the system.',
        details: {
            po_number: 'PO-MISSING-999',
            vendor_id: 'V001',
            invoice_amount: '$2,160.00',
        },
        owner_role: 'ap_manager',
        sla_deadline: '2024-01-19 18:00',
        sla_breached: false,
        created_at: '2024-01-18 10:00',
    }
}

export default async function ExceptionDetailPage({ params }: { params: { id: string } }) {
    const exception = await getException(params.id)

    return (
        <div>
            <div className="flex items-center gap-4 mb-6">
                <Link href="/exceptions" className="text-gray-500 hover:text-gray-700">
                    ← Back to Exceptions
                </Link>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    {/* Exception Details */}
                    <div className="card">
                        <div className="flex justify-between items-start mb-4">
                            <div>
                                <h1 className="text-xl font-bold text-gray-900">{exception.title}</h1>
                                <p className="text-gray-500 capitalize">{exception.category.replace('_', ' ')}</p>
                            </div>
                            <span className={`status-badge severity-${exception.severity}`}>
                                {exception.severity}
                            </span>
                        </div>

                        <p className="text-gray-700 mb-4">{exception.description}</p>

                        <dl className="grid grid-cols-2 gap-4 border-t border-gray-200 pt-4">
                            <div>
                                <dt className="text-sm text-gray-500">Invoice</dt>
                                <dd>
                                    <Link href={`/invoices/${exception.invoice_id}`} className="text-primary-600 hover:text-primary-800">
                                        {exception.invoice_number}
                                    </Link>
                                </dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">Owner Role</dt>
                                <dd className="text-sm font-medium text-gray-900 capitalize">{exception.owner_role.replace('_', ' ')}</dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">Created</dt>
                                <dd className="text-sm font-medium text-gray-900">{exception.created_at}</dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">SLA Deadline</dt>
                                <dd className={`text-sm font-medium ${exception.sla_breached ? 'text-red-600' : 'text-gray-900'}`}>
                                    {exception.sla_deadline}
                                    {exception.sla_breached && ' (Breached)'}
                                </dd>
                            </div>
                        </dl>
                    </div>

                    {/* Exception Details JSON */}
                    <div className="card">
                        <h2 className="text-lg font-medium text-gray-900 mb-4">Details</h2>
                        <pre className="bg-gray-50 p-4 rounded-md text-sm overflow-auto">
                            {JSON.stringify(exception.details, null, 2)}
                        </pre>
                    </div>
                </div>

                {/* Resolution Form */}
                <div className="card">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Resolution</h2>
                    <form className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Action
                            </label>
                            <select className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm">
                                <option value="">Select action...</option>
                                <option value="approve">Approve Invoice</option>
                                <option value="reject">Reject Invoice</option>
                                <option value="escalate">Escalate</option>
                                <option value="reprocess">Reprocess</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Resolution Notes
                            </label>
                            <textarea
                                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                                rows={4}
                                placeholder="Explain the resolution decision..."
                            />
                        </div>
                        <button type="submit" className="btn-primary w-full">
                            Resolve Exception
                        </button>
                    </form>
                </div>
            </div>
        </div>
    )
}
