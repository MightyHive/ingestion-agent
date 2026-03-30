export default function Header() {
    return (
      <header className="fixed top-0 w-full z-50 flex justify-between items-center px-6 h-16 bg-white">
  
        {/* Izquierda: logo */}
        <div className="flex items-center gap-8">
          <span className="text-xl font-bold tracking-tight text-slate-900">Media Data Studio</span>
  
          {/* Nav links */}
          <nav className="flex items-center gap-6">
            <a href="#" className="text-blue-600 font-semibold border-b-2 border-blue-600 py-1">Home</a>
            <a href="#" className="text-slate-500 hover:text-slate-700 transition-colors py-1">Pipelines</a>
            <a href="#" className="text-slate-500 hover:text-slate-700 transition-colors py-1">Settings</a>
          </nav>
        </div>
  
        {/* Derecha: íconos + avatar */}
        <div className="flex items-center gap-2">
          <button className="p-2 hover:bg-slate-50 rounded-lg transition-colors">
            <span className="material-symbols-outlined text-slate-500">help</span>
          </button>
          <button className="p-2 hover:bg-slate-50 rounded-lg transition-colors">
            <span className="material-symbols-outlined text-slate-500">notifications</span>
          </button>
          <div className="w-8 h-8 rounded-full bg-slate-300 ml-2" />
        </div>
  
      </header>
    )
  }