import { NavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ClipboardList, Video, Map as MapIcon, Activity, Fingerprint, Car, Radio, Network, Power, FlaskConical } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import AlertCenter from './components/AlertCenter';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export default function Layout() {
    const { t } = useTranslation();

    return (
        <div className="min-h-screen bg-background flex flex-col font-sans selection:bg-accent-amber/30 selection:text-white">
            {/* TAB SWITCHER & TACTICAL ALERT CENTER */}
            <nav className="relative z-[60] glass-panel h-10 px-8 flex items-center justify-between shrink-0 overflow-x-auto custom-scrollbar">
                <div className="flex items-center gap-2">
                    <TabLink to="/" label={t('nav.catalog')} icon={<ClipboardList className="w-3.5 h-3.5" />} />
                    <TabLink to="/cameras" label={t('nav.cameras')} icon={<Video className="w-3.5 h-3.5" />} />
                    <TabLink to="/map" label="MAPA GEO" icon={<MapIcon className="w-3.5 h-3.5" />} />
                    <TabLink to="/painel" label="PAINEL" icon={<Activity className="w-3.5 h-3.5" />} />
                    <TabLink to="/ao-vivo" label="AO VIVO" icon={<Radio className="w-3.5 h-3.5" />} />
                    <TabLink to="/pessoas" label="PESSOAS" icon={<Fingerprint className="w-3.5 h-3.5" />} />
                    <TabLink to="/veiculos" label="VEÍCULOS" icon={<Car className="w-3.5 h-3.5" />} />
                    <TabLink to="/tatico" label="TÁTICO" icon={<Network className="w-3.5 h-3.5" />} />
                    <TabLink to="/controle" label="CONTROLE" icon={<Power className="w-3.5 h-3.5" />} />
                    <TabLink to="/cameras-teste" label="CÂMERAS TESTE" icon={<FlaskConical className="w-3.5 h-3.5" />} />
                </div>
                <div className="flex items-center gap-3">
                    <AlertCenter />
                </div>
            </nav>

            <div className="flex-1 flex flex-col min-h-0">
                <Outlet />
            </div>
        </div>
    );
}

function TabLink({ to, label, icon }: { to: string; label: string; icon: React.ReactNode }) {
    return (
        <NavLink
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
                cn(
                    'h-7 px-4 rounded-full text-[10px] font-black tracking-widest uppercase flex items-center gap-2 transition-all',
                    isActive ? 'bg-accent-amber text-black' : 'text-muted hover:bg-white/5 hover:text-white'
                )
            }
        >
            {icon} {label}
        </NavLink>
    );
}
