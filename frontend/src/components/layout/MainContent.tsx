"use client"

import PageHelp from "@/components/layout/PageHelp"

export default function MainContent({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHelp />
      {children}
    </>
  )
}
