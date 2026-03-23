"use client";

import { AlertTriangle, CheckCircle, Info } from "lucide-react";

interface Props {
  hallucinationFlag: boolean;
  confidenceScore: number | null;
  flaggedClaims?: string[];
  onViewSources?: () => void;
}

export function HallucinationWarning({
  hallucinationFlag,
  confidenceScore,
  flaggedClaims = [],
  onViewSources,
}: Props) {
  const score = confidenceScore ?? 0;
  const pct = Math.round(score * 100);

  const color =
    pct >= 85 ? "green" : pct >= 60 ? "yellow" : "red";

  const colorClasses = {
    green: "bg-green-50 border-green-200 text-green-800",
    yellow: "bg-yellow-50 border-yellow-200 text-yellow-800",
    red: "bg-red-50 border-red-200 text-red-800",
  };

  const Icon = hallucinationFlag ? AlertTriangle : pct >= 85 ? CheckCircle : Info;

  return (
    <div className={`flex flex-col gap-2 rounded-lg border p-3 text-sm ${colorClasses[color]}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 shrink-0" />
          <span className="font-medium">
            {hallucinationFlag
              ? "Doğrulanamayan iddia tespit edildi"
              : pct >= 85
              ? "Yüksek kaynak güveni"
              : "Orta kaynak güveni – lütfen kaynakları kontrol edin"}
          </span>
        </div>
        <span className="font-mono text-xs font-bold">%{pct}</span>
      </div>

      {flaggedClaims.length > 0 && (
        <ul className="ml-6 list-disc text-xs">
          {flaggedClaims.map((claim, i) => (
            <li key={i}>{claim}</li>
          ))}
        </ul>
      )}

      {onViewSources && (
        <button
          onClick={onViewSources}
          className="mt-1 self-start text-xs underline underline-offset-2 hover:no-underline"
        >
          Kaynakları Görüntüle
        </button>
      )}
    </div>
  );
}
