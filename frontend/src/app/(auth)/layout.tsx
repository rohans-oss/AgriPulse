export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-brand text-xs font-bold text-white">AF</span>
          <div>
            <div className="text-sm font-semibold">AgriFlow AI</div>
            <div className="text-xs text-ink-2">Agricultural supply-chain intelligence</div>
          </div>
        </div>
        <div className="rounded-lg border border-line bg-surface p-6">{children}</div>
      </div>
    </div>
  );
}
