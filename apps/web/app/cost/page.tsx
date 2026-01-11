interface CostMetrics {
    total_cost: string
    avg_cost_per_invoice: string
    avg_cost_per_verified: string
    touchless_rate: number
    cache_hit_rate: number
    cost_by_tier: Array<{
        tier: string
        cost: string
        calls: number
        percentage: number
    }>
    cost_by_exception: Array<{
        category: string
        cost: string
        count: number
    }>
}

async function getCostMetrics(): Promise<CostMetrics> {
    return {
        total_cost: '$0.23',
        avg_cost_per_invoice: '$0.023',
        avg_cost_per_verified: '$0.038',
        touchless_rate: 60,
        cache_hit_rate: 33,
        cost_by_tier: [
            { tier: 'Tier A (GPT-3.5)', cost: '$0.05', calls: 6, percentage: 22 },
            { tier: 'Tier B (GPT-4-mini)', cost: '$0.12', calls: 3, percentage: 52 },
            { tier: 'Tier C (GPT-4)', cost: '$0.06', calls: 1, percentage: 26 },
        ],
        cost_by_exception: [
            { category: 'Amount Variance', cost: '$0.04', count: 2 },
            { category: 'Missing PO', cost: '$0.02', count: 1 },
            { category: 'Duplicate', cost: '$0.01', count: 1 },
        ],
    }
}

export default async function CostDashboardPage() {
    const metrics = await getCostMetrics()

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-6">Cost Dashboard</h1>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
                <div className="card">
                    <dt className="text-sm font-medium text-gray-500">Total LLM Cost</dt>
                    <dd className="mt-1 text-3xl font-semibold text-gray-900">{metrics.total_cost}</dd>
                </div>
                <div className="card">
                    <dt className="text-sm font-medium text-gray-500">Avg Cost / Invoice</dt>
                    <dd className="mt-1 text-3xl font-semibold text-gray-900">{metrics.avg_cost_per_invoice}</dd>
                </div>
                <div className="card">
                    <dt className="text-sm font-medium text-gray-500">Avg Cost / Verified</dt>
                    <dd className="mt-1 text-3xl font-semibold text-gray-900">{metrics.avg_cost_per_verified}</dd>
                </div>
                <div className="card">
                    <dt className="text-sm font-medium text-gray-500">Cache Hit Rate</dt>
                    <dd className="mt-1 text-3xl font-semibold text-green-600">{metrics.cache_hit_rate}%</dd>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Cost by Model Tier */}
                <div className="card">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Cost by Model Tier</h2>
                    <div className="space-y-4">
                        {metrics.cost_by_tier.map((tier) => (
                            <div key={tier.tier}>
                                <div className="flex justify-between text-sm mb-1">
                                    <span className="font-medium">{tier.tier}</span>
                                    <span className="text-gray-500">{tier.cost} ({tier.calls} calls)</span>
                                </div>
                                <div className="w-full bg-gray-200 rounded-full h-2">
                                    <div
                                        className="bg-primary-600 h-2 rounded-full"
                                        style={{ width: `${tier.percentage}%` }}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-4 pt-4 border-t border-gray-200 text-sm text-gray-500">
                        <p>Tier A: $0.0001/1K tokens • Tier B: $0.001/1K • Tier C: $0.01/1K</p>
                    </div>
                </div>

                {/* Cost by Exception Type */}
                <div className="card">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Cost by Exception Type</h2>
                    <div className="overflow-hidden">
                        <table className="min-w-full">
                            <thead>
                                <tr className="border-b border-gray-200">
                                    <th className="text-left text-xs font-medium text-gray-500 uppercase py-2">Category</th>
                                    <th className="text-right text-xs font-medium text-gray-500 uppercase py-2">Count</th>
                                    <th className="text-right text-xs font-medium text-gray-500 uppercase py-2">Cost</th>
                                </tr>
                            </thead>
                            <tbody>
                                {metrics.cost_by_exception.map((exc) => (
                                    <tr key={exc.category} className="border-b border-gray-100">
                                        <td className="py-3 text-sm text-gray-900">{exc.category}</td>
                                        <td className="py-3 text-sm text-gray-500 text-right">{exc.count}</td>
                                        <td className="py-3 text-sm font-medium text-gray-900 text-right">{exc.cost}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Efficiency Metrics */}
                <div className="card lg:col-span-2">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Efficiency Metrics</h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-2xl font-bold text-green-600">{metrics.touchless_rate}%</div>
                            <div className="text-sm text-gray-500">Touchless Rate</div>
                        </div>
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-2xl font-bold text-blue-600">{metrics.cache_hit_rate}%</div>
                            <div className="text-sm text-gray-500">Cache Hit Rate</div>
                        </div>
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-2xl font-bold text-gray-900">10</div>
                            <div className="text-sm text-gray-500">Total Invoices</div>
                        </div>
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-2xl font-bold text-orange-600">4</div>
                            <div className="text-sm text-gray-500">Exceptions</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
