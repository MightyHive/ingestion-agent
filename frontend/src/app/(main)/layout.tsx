import Header from "@/components/layout/Header"
import MainContent from "@/components/layout/MainContent"
import Sidebar from "@/components/layout/Sidebar"

export default function MainLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <>
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="ml-64 mt-16 flex-1 p-8">
          <MainContent>{children}</MainContent>
        </main>
      </div>
    </>
  )
}
