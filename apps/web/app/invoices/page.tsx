import Link from 'next/link'

interface Invoice {
    id: string
    invoice_number: string
    vendor_name: string
    total_amount: string
    status: string
    created_at: string
}

async function getInvoices(): Promise<Invoice[]> {
    // Mock data for demo
    return [
        { id: '1', invoice_number: 'INV-2024-001', vendor_name: 'Acme Supplies Inc', total_amount: '$5,400.00', status: 'approved', created_at: '2024-01-15' },
        { id: '2', invoice_number: 'INV-2024-002', vendor_name: 'Tech Components LLC', total_amount: '$3,456.00', status: 'approved', created_at: '2024-01-17' },
        { id: '3', invoice_number: 'INV-2024-003', vendor_name: 'Acme Supplies Inc', total_amount: '$2,160.00', status: 'exception', created_at: '2024-01-18' },
        { id: '4', invoice_number: 'INV-2024-004', vendor_name: 'Acme Supplies Inc', total_amount: '$5,400.00', status: 'exception', created_at: '2024-01-15' },
        { id: '5', invoice_number: 'INV-2024-005', vendor_name: 'Acme Supplies Inc', total_amount: '$1,944.00', status: 'exception', created_at: '2024-01-20' },
        { id: '6', invoice_number: 'INV-2024-006', vendor_name: 'Office Solutions Co', total_amount: '$864.00', status: 'approved', created_at: '2024-01-23' },
        { id: '7', invoice_number: 'INV-2024-007', vendor_name: 'Tech Components LLC', total_amount: '$3,456.00', status: 'exception', created_at: '2024-01-17' },
        { id: '8', invoice_number: 'INV-2024-008', vendor_name: 'Tech Components LLC', total_amount: '$12,960.00', status: 'approved', created_at: '2024-01-26' },
        { id: '9', invoice_number: 'INV-2024-009', vendor_name: 'Unknown Vendor Corp', total_amount: '$1,620.00', status: 'exception', created_at: '2024-01-21' },
        { id: '10', invoice_number: 'INV-2024-010', vendor_name: 'Acme Supplies Inc', total_amount: '$5,389.20', status: 'approved', created_at: '2024-01-28' },
    ]
}

function getStatusClass(status: string): string {
    const statusMap: Record<string, string> = {
        pending: 'status-pending',
        processing: 'status-processing',
        approved: 'status-approved',
        exception: 'status-exception',
        rejected: 'status-exception',
    }
    return statusMap[status] || 'status-pending'
}

export default async function InvoicesPage() {
    const invoices = await getInvoices()

    return (
        <div>
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold text-gray-900">Invoices</h1>
                <div className="flex gap-2">
                    <select className="border border-gray-300 rounded-md px-3 py-2 text-sm">
                        <option value="">All Statuses</option>
                        <option value="pending">Pending</option>
                        <option value="approved">Approved</option>
                        <option value="exception">Exception</option>
                    </select>
                </div>
            </div>

            <div className="card overflow-hidden p-0">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Invoice
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Vendor
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Amount
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Status
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Date
                            </th>
                            <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Actions
                            </th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {invoices.map((invoice) => (
                            <tr key={invoice.id} className="hover:bg-gray-50">
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <Link href={`/invoices/${invoice.id}`} className="text-primary-600 hover:text-primary-800 font-medium">
                                        {invoice.invoice_number}
                                    </Link>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                    {invoice.vendor_name}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">
                                    {invoice.total_amount}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className={`status-badge ${getStatusClass(invoice.status)}`}>
                                        {invoice.status}
                                    </span>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                    {invoice.created_at}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                                    <Link href={`/invoices/${invoice.id}`} className="text-primary-600 hover:text-primary-800">
                                        View
                                    </Link>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
