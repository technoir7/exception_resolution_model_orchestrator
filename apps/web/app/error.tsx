'use client'

export default function Failed({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
    return (
        <div className="card max-w-xl">
            <h1 className="text-lg font-semibold text-gray-900 mb-2">This page could not be loaded</h1>
            <p className="text-sm text-gray-700 mb-4">{error.message || 'The API returned an error.'}</p>
            <button onClick={reset} className="btn-secondary text-sm">Try again</button>
        </div>
    )
}
