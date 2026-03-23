# LexAI – Hukuk Bürosu Yapay Zeka Platformu

**"AI Avukatın Yerini Almayacak, Avukatın Verimliliğini 10x Artıracak"**

Türk hukuk büroları için RAG tabanlı, kanıt odaklı yapay zeka asistanı.
AWS Bedrock (Claude 3.5 Sonnet) + pgvector + Next.js 14

---

## Mimari

```
Frontend (Next.js 14)
    ↕  REST + SSE
Backend (FastAPI)
    ├── RAG Pipeline
    │   ├── AWS Textract (OCR)
    │   ├── AWS Bedrock Titan (Embeddings)
    │   └── pgvector (Similarity Search)
    ├── Claude 3.5 Sonnet (via AWS Bedrock)
    └── Hallucination Guard (2-aşamalı)
PostgreSQL + pgvector
Redis (Rate limiting & cache)
```

## 20 Hukuki Prompt Şablonu

| # | Şablon | Kategori | Açıklama |
|---|--------|----------|----------|
| 1 | `contract_review` | Belge Analizi | TBK/TTK çerçevesinde sözleşme incelemesi |
| 2 | `risk_assessment` | Belge Analizi | JSON formatında risk değerlendirmesi |
| 3 | `clause_extraction` | Belge Analizi | Madde çıkarma ve sınıflandırma |
| 4 | `compliance_check` | Belge Analizi | KVKK/TTK/TBK uyum denetimi |
| 5 | `summary_generation` | Belge Analizi | Avukat + müvekkil özeti |
| 6 | `case_law_analysis` | Hukuki Analiz | İçtihat analizi (critical guard) |
| 7 | `statute_interpretation` | Hukuki Analiz | 4 yorum yöntemi |
| 8 | `precedent_comparison` | Hukuki Analiz | Emsal karşılaştırma matrisi |
| 9 | `legal_opinion` | Hukuki Analiz | Resmi görüş yazısı taslağı |
| 10 | `contract_drafting` | Yazım Desteği | TBK uyumlu sözleşme taslağı |
| 11 | `petition_drafting` | Yazım Desteği | HMK 119 uyumlu dilekçe |
| 12 | `legal_letter` | Yazım Desteği | İhtarname / KEP formatı |
| 13 | `amendment_drafting` | Yazım Desteği | Ek protokol / zeyilname |
| 14-16 | RAG system prompts | Sistem | Uydurma engelleyici, atıf formatı |
| 17 | `case_summary` | Sunum | Dava durum raporu + risk skoru |
| 18 | `legal_brief` | Sunum | Hukuki bülten / sunum |

## Hızlı Başlangıç

```bash
# 1. Repoyu klonla
git clone https://github.com/KULLANICI_ADI/lexai.git
cd lexai

# 2. Ortam değişkenlerini hazırla
cp .env.example .env
# .env dosyasını düzenle: AWS credentials, DB passwords, JWT secrets

# 3. Geliştirme ortamını başlat
make dev

# 4. Migration çalıştır
make migrate

# 5. Uygulama açık:
# Backend API:  http://localhost:8000/docs
# Frontend:     http://localhost:3000
```

## Güvenlik Özellikleri

### Hallucination Guard (2 Aşamalı)
1. **Lexical Overlap** – Jaccard similarity ile hızlı kaynak uyumu kontrolü
2. **Critical Mode** – Yargıtay karar numaralarını kaynak belgelerle karşılaştırır

### Tenant İzolasyonu
- Her hukuk bürosu için ayrı PostgreSQL schema
- JWT + API key kimlik doğrulama
- Row-level tenant_id filtreleme

### Veri Güvenliği
- Belgeler AWS S3'te şifreli saklanır
- AWS Textract OCR – veriler AWS sınırları içinde kalır
- Bedrock – Anthropic'e veri gönderilmez (AWS'nin kendi altyapısı)

## Proje Yapısı

```
lexai/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI route'ları
│   │   ├── core/            # Config, security, exceptions
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── prompts/         # 20 hukuki prompt şablonu
│   │   ├── rag/             # RAG pipeline, chunker, citation tracker
│   │   └── services/        # Bedrock, OCR, embedding, hallucination guard
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/             # Next.js 14 App Router
│       ├── components/      # CitationPanel, HallucinationWarning, vb.
│       └── lib/             # API client
├── infrastructure/
│   ├── postgres/            # init.sql, pgvector setup
│   └── docker/nginx/        # Reverse proxy config
└── .github/workflows/       # CI/CD pipeline
```

## Sunum Noktaları

- **"AI uydurur mu?"** → Hallucination Guard: 2 aşamalı doğrulama, her iddiaya kaynak zorunluluğu
- **"Verilerim çalınır mı?"** → AWS Bedrock = veriler Anthropic'e gitmez, tenant schema izolasyonu
- **Zaman tasarrufu** → 30 sayfalık rapor → 30 saniyede özet

## Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| AI Modeli | Claude 3.5 Sonnet (AWS Bedrock) |
| Embedding | Amazon Titan Embeddings v2 (1536d) |
| OCR | AWS Textract |
| Vector DB | PostgreSQL + pgvector (ivfflat) |
| Backend | FastAPI + SQLAlchemy async |
| Frontend | Next.js 14 + TypeScript + Tailwind |
| Auth | JWT + bcrypt |
| Cache | Redis |
| Deploy | Docker + GitHub Actions + AWS ECR |
