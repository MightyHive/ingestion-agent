"use client"

import { signIn } from "next-auth/react"
import { useState } from "react"

function GoogleMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden>
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  )
}

export default function LoginPage() {
  const [busy, setBusy] = useState(false)

  async function handleGoogle() {
    setBusy(true)
    try {
      await signIn("google", { callbackUrl: "/" })
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-screen w-full flex-col bg-[#fcf8ff] text-[#1a1a2e] md:flex-row">
      <section className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-[#1a1a2e] p-16 md:flex">
        <div className="pointer-events-none absolute inset-0 opacity-20">
          <div className="absolute left-[-10%] top-[-10%] h-[60%] w-[60%] rounded-full bg-[#316af7] blur-[120px]" />
          <div className="absolute bottom-[-5%] right-[-5%] h-[40%] w-[40%] rounded-full bg-[#5d50b2] blur-[100px]" />
        </div>

        <div className="relative z-10">
          <div className="mb-12 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#004fda] to-[#316af7] shadow-lg">
              <span
                className="material-symbols-outlined text-xl text-white"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                dataset
              </span>
            </div>
            <span className="text-2xl font-extrabold tracking-tighter text-white">Media Data Studio</span>
          </div>

          <div className="max-w-md">
            <h1 className="mb-6 text-5xl font-bold leading-tight tracking-tight text-white">
              Your data pipelines, on autopilot.
            </h1>
            <ul className="space-y-6">
              {[
                {
                  title: "AI agents",
                  body: "Autonomous entities that monitor, clean, and optimize your data streams 24/7.",
                },
                {
                  title: "Credential management",
                  body: "Secure vaulting for API keys and OAuth tokens.",
                },
                {
                  title: "BigQuery-native",
                  body: "Orchestrate data into your GCP workspace with minimal friction.",
                },
              ].map((item) => (
                <li key={item.title} className="flex items-start gap-4">
                  <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#004fda]/30 bg-[#004fda]/20">
                    <span
                      className="material-symbols-outlined text-sm text-[#5c9dff]"
                      style={{ fontVariationSettings: "'wght' 700" }}
                    >
                      check
                    </span>
                  </div>
                  <div>
                    <h3 className="font-semibold text-white">{item.title}</h3>
                    <p className="text-sm leading-relaxed text-[#c3c5d7]">{item.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="relative z-10 mt-auto border border-white/10 bg-white/5 p-4 pt-12 backdrop-blur-sm">
          <div className="rounded-xl bg-gradient-to-br from-[#316af7]/30 to-[#5d50b2]/20 p-8">
            <p className="text-center text-sm text-white/70">
              Sign in with your Google workspace account to continue.
            </p>
          </div>
        </div>
      </section>

      <section className="flex w-full flex-col items-center justify-center bg-[#fcf8ff] p-8 md:w-1/2 md:p-24">
        <div className="flex w-full max-w-sm flex-col gap-8">
          <div className="mb-4 flex items-center gap-3 md:hidden">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#004fda]">
              <span className="material-symbols-outlined text-base text-white">dataset</span>
            </div>
            <span className="text-xl font-bold tracking-tighter text-[#1a1a2e]">Media Data Studio</span>
          </div>

          <div className="space-y-2">
            <h2 className="text-3xl font-bold tracking-tight text-[#1a1a2e]">Welcome back</h2>
            <p className="text-sm text-muted-foreground">
              Sign in with Google to manage your pipelines and exports.
            </p>
          </div>

          <button
            type="button"
            disabled={busy}
            onClick={() => void handleGoogle()}
            className="flex w-full items-center justify-center gap-3 rounded-xl border border-border bg-white px-4 py-3 font-medium text-foreground shadow-sm transition-colors hover:bg-muted/60 disabled:pointer-events-none disabled:opacity-60"
          >
            <GoogleMark className="h-5 w-5 shrink-0" />
            {busy ? "Redirecting…" : "Sign in with Google"}
          </button>

          <footer className="mt-8 flex flex-col gap-4 border-t border-border/60 pt-8 text-center">
            <div className="flex justify-center gap-6 text-xs font-medium text-muted-foreground">
              <span className="cursor-default">Privacy</span>
              <span className="cursor-default">Terms</span>
              <span className="cursor-default">Support</span>
            </div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/80">
              © {new Date().getFullYear()} Media Data Studio
            </p>
          </footer>
        </div>
      </section>
    </main>
  )
}
