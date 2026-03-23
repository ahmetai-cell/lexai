#!/usr/bin/env python3
"""
CLI: Embedding model kalite testi
Çalıştırma: python scripts/evaluate_embedding.py
"""
import asyncio
import json
import sys
import os

# Backend kök dizinini path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.embedding_evaluator import EmbeddingEvaluator, LEGAL_TERM_PAIRS


async def main():
    print("\n🔍 LexAI Embedding Model Kalite Testi başlatılıyor...\n")

    evaluator = EmbeddingEvaluator(threshold=0.85)
    report = await evaluator.run()

    # Konsol raporu
    print(report.summary())

    # JSON çıktı
    output_path = "embedding_eval_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"\n📄 Detaylı rapor: {output_path}")

    # Exit code: 0=başarılı, 1=yetersiz
    sys.exit(0 if report.verdict == "UYGUN" else 1)


if __name__ == "__main__":
    asyncio.run(main())
