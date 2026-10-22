import { logIn } from '@/app/actions'
import { ErrorBanner } from '@/app/ui'

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ failed?: string }> }) {
    const { failed } = await searchParams
    return (
        <div className="max-w-sm mx-auto mt-16">
            <h1 className="text-2xl font-bold text-gray-900 mb-6">Log in</h1>
            <ErrorBanner message={failed ? 'Wrong username or password.' : undefined} />
            <form action={logIn} className="card space-y-4">
                <label className="block">
                    <span className="block text-sm font-medium text-gray-700 mb-1">Username</span>
                    <input name="username" required autoComplete="username" className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
                </label>
                <label className="block">
                    <span className="block text-sm font-medium text-gray-700 mb-1">Password</span>
                    <input name="password" type="password" required autoComplete="current-password" className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
                </label>
                <button type="submit" className="btn-primary w-full">Log in</button>
            </form>
            <p className="mt-4 text-sm text-gray-500">
                Demo accounts: <code>controller</code>, <code>ap_manager</code> or <code>bpo_operator</code>, password <code>demo123</code>.
            </p>
        </div>
    )
}
