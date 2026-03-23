import { LoginButton } from "./login-button";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-bg-base px-6">
      <div className="max-w-lg text-center">
        {/* Logo */}
        <h1 className="text-5xl font-bold text-text-primary tracking-tight">
          BLOASIS
        </h1>
        <p className="mt-3 text-lg text-text-secondary">
          AI-Powered Multi-Asset Trading Platform
        </p>

        {/* Features */}
        <div className="mt-10 grid grid-cols-3 gap-4 text-center">
          <div className="p-4 rounded-xl bg-bg-elevated border border-border-custom">
            <div className="text-2xl mb-2">📊</div>
            <p className="text-xs font-medium text-text-secondary">
              Market Regime Analysis
            </p>
          </div>
          <div className="p-4 rounded-xl bg-bg-elevated border border-border-custom">
            <div className="text-2xl mb-2">🤖</div>
            <p className="text-xs font-medium text-text-secondary">
              AI Signal Generation
            </p>
          </div>
          <div className="p-4 rounded-xl bg-bg-elevated border border-border-custom">
            <div className="text-2xl mb-2">⚡</div>
            <p className="text-xs font-medium text-text-secondary">
              Automated Execution
            </p>
          </div>
        </div>

        {/* CTA */}
        <div className="mt-10">
          <LoginButton />
        </div>

        <p className="mt-6 text-xs text-text-muted">
          Deterministic risk rules &middot; 6-factor scoring &middot; Paper
          trading by default
        </p>
      </div>
    </main>
  );
}
