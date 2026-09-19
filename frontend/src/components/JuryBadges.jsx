import { useLanguage } from '../hooks/useLanguage.jsx'

export default function JuryBadges() {
  const { t } = useLanguage()
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="rounded-full border border-mint/40 bg-ink px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider text-mint">
        {t('MASAK Uyumlu (SEP-6)', 'FCIB Compliant (SEP-6)')}
      </span>
      <span className="rounded-full border border-ink/15 bg-white/80 px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider text-ink/80">
        {t('Otonom Ajan Mutabakatı', 'Autonomous Agent Settlement')}
      </span>
    </div>
  )
}
