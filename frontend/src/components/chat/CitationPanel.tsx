"use client";

import { CitationMap, SourceChunk } from "@/types/api";
import { FileText, Scale, BookOpen } from "lucide-react";

interface Props {
  citationMap: CitationMap | null;
  sources: SourceChunk[];
}

export function CitationPanel({ citationMap, sources }: Props) {
  if (!citationMap && sources.length === 0) return null;

  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4">
      <h3 className="text-sm font-semibold text-gray-700">Kaynaklar & Atıflar</h3>

      {/* Belge kaynakları */}
      {sources.length > 0 && (
        <section>
          <div className="mb-2 flex items-center gap-1 text-xs font-medium text-gray-500">
            <FileText className="h-3 w-3" />
            <span>BELGELER ({sources.length})</span>
          </div>
          <div className="flex flex-col gap-2">
            {sources.map((s, i) => (
              <SourceCard key={i} source={s} index={i + 1} />
            ))}
          </div>
        </section>
      )}

      {/* Kanun atıfları */}
      {citationMap && citationMap.law_refs.length > 0 && (
        <section>
          <div className="mb-2 flex items-center gap-1 text-xs font-medium text-gray-500">
            <Scale className="h-3 w-3" />
            <span>KANUN MADDE ({citationMap.law_refs.length})</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {citationMap.law_refs.map((ref, i) => (
              <span key={i} className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
                {ref.law} m.{ref.article}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Yargıtay kararları */}
      {citationMap && citationMap.case_refs.length > 0 && (
        <section>
          <div className="mb-2 flex items-center gap-1 text-xs font-medium text-gray-500">
            <BookOpen className="h-3 w-3" />
            <span>YARGITAY KARARLARI ({citationMap.case_refs.length})</span>
          </div>
          <div className="flex flex-col gap-1">
            {citationMap.case_refs.map((ref, i) => (
              <div key={i} className="rounded bg-amber-50 p-2 text-xs text-amber-900">
                Yargıtay {ref.chamber}. HD — {ref.date} — E.{ref.case_no}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function SourceCard({ source, index }: { source: SourceChunk; index: number }) {
  const similarity = Math.round(source.similarity * 100);
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 text-xs shadow-sm">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-medium text-gray-700">Kaynak {index}</span>
        <span className="text-gray-400">Sayfa {source.page ?? "?"} · %{similarity}</span>
      </div>
      <p className="line-clamp-3 text-gray-600">{source.text_snippet}</p>
    </div>
  );
}
