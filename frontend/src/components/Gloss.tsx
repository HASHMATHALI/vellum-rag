import React, { useState } from 'react';
import type { GlossReport, GlossStatus } from '../hooks/useChat';

// The gloss is the margin note beside an answer: how many of its claims are
// actually found in the passages it cites. Computed on the server without a
// model (see backend/app/retrieval/gloss.py), so it is a wording check, not a
// judgement of truth.

const LABEL: Record<GlossStatus, string> = {
  supported: 'Found in cited passage',
  partial: 'Partly found',
  unsupported: 'Not found in cited passage',
  phantom: 'Cites a passage that was not retrieved',
  traceable: 'No citation, but found in a passage',
  uncited: 'No citation, not found',
};

const TONE: Record<GlossStatus, string> = {
  supported: 'border-emerald-700 text-emerald-800 dark:border-emerald-500 dark:text-emerald-400',
  traceable: 'border-emerald-700 text-emerald-800 dark:border-emerald-500 dark:text-emerald-400',
  partial: 'border-amber-600 text-amber-700 dark:border-amber-400 dark:text-amber-300',
  unsupported: 'border-rubric text-rubric dark:border-rubric-light dark:text-rubric-light',
  phantom: 'border-rubric text-rubric dark:border-rubric-light dark:text-rubric-light',
  uncited: 'border-zinc-400 text-zinc-600 dark:border-zinc-500 dark:text-zinc-400',
};

const MARK: Record<GlossStatus, string> = {
  supported: '✓', traceable: '✓', partial: '~', unsupported: '✗', phantom: '✗', uncited: '?',
};

const ORDER: GlossStatus[] = ['phantom', 'unsupported', 'partial', 'uncited', 'traceable', 'supported'];

export const Gloss: React.FC<{ report: GlossReport }> = ({ report }) => {
  const [open, setOpen] = useState(false);
  const { summary, claims } = report;
  if (!summary || summary.total === 0) return null;

  const grounded = summary.supported + summary.traceable;
  const problems = summary.phantom + summary.unsupported;
  const sorted = [...claims].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));

  return (
    <section className="w-full border-l-2 border-rubric/70 dark:border-rubric-light/70 pl-3.5 mt-1" aria-label="Citation check">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full text-left flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[11px] text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <span className="font-display text-sm text-rubric dark:text-rubric-light">Gloss</span>
        <span>
          <b className="font-mono text-zinc-900 dark:text-zinc-100">{grounded}</b> of{' '}
          <b className="font-mono text-zinc-900 dark:text-zinc-100">{summary.total}</b> claims found in your documents
        </span>
        {problems > 0 && (
          <span className="text-rubric dark:text-rubric-light font-semibold">
            {problems} citation{problems === 1 ? '' : 's'} to check
          </span>
        )}
        {summary.uncited > 0 && <span>{summary.uncited} without a source</span>}
        <span className="ml-auto underline underline-offset-2">{open ? 'Hide' : 'Show claims'}</span>
      </button>

      {open && (
        <div className="mt-2.5">
          <ol className="space-y-2">
            {sorted.map((claim, idx) => (
              <li key={idx} className="text-xs leading-relaxed flex gap-2.5">
                <span
                  className={`shrink-0 w-5 h-5 mt-0.5 border rounded-sm font-mono text-[11px] flex items-center justify-center ${TONE[claim.status]}`}
                  aria-hidden="true"
                >
                  {MARK[claim.status]}
                </span>
                <div className="min-w-0">
                  <p className="text-zinc-800 dark:text-zinc-200">{claim.text}</p>
                  <p className={`text-[11px] font-semibold ${TONE[claim.status].replace(/border-\S+/g, '')}`}>
                    {LABEL[claim.status]}
                    {claim.citations.length > 0 && (
                      <span className="font-normal text-zinc-500 dark:text-zinc-400">
                        {' · '}
                        {claim.citations.map((c) => `${c.filename} p.${c.page}`).join(', ')}
                      </span>
                    )}
                    {claim.status !== 'phantom' && (
                      <span className="font-normal font-mono text-zinc-500 dark:text-zinc-400">
                        {' · '}{Math.round(claim.support * 100)}% of terms
                      </span>
                    )}
                  </p>
                  {claim.notes.map((note, nIdx) => (
                    <p key={nIdx} className="text-[11px] text-zinc-500 dark:text-zinc-400">{note}</p>
                  ))}
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[10px] text-zinc-500 dark:text-zinc-500 max-w-prose">
            This compares the wording of each sentence with the passages it cites. It catches missing or wrong
            citations and figures; it cannot tell whether a paraphrase is faithful. Read the passage before relying on a claim.
          </p>
        </div>
      )}
    </section>
  );
};
