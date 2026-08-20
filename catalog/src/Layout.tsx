import { NavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ClipboardList, Video } from 'lucide-react';
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
            <nav className="relative z-[60] glass-panel h-10 px-8 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                    <TabLink to="/" label={t('nav.catalog')} icon={<ClipboardList className="w-3.5 h-3.5" />} />
                    <TabLink to="/cameras" label={t('nav.cameras')} icon={<Video className="w-3.5 h-3.5" />} />
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
