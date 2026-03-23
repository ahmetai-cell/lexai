from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="rag_fallback",
    category="rag_system",
    display_name_tr="Kaynak Bulunamadı Yanıtı",
    display_name_en="RAG Fallback Response",
    description_tr="Retrieval sonuç döndürmediğinde kullanılan fallback. İç kullanım.",
    system_prompt="""Kullanıcının sorusuna yanıt vermek için yeterli kaynak bulunamadı.

Şu şekilde yanıt ver:

"Sorunuzla ilgili yüklenen belgeler arasında yeterli bilgi bulunamadı.

Olası nedenler:
- İlgili belge henüz sisteme yüklenmemiş olabilir
- Soru farklı bir alanda olabilir

Öneriler:
1. İlgili belgeyi sisteme yükleyin
2. Soruyu farklı kelimelerle tekrar deneyin
3. Büro uzmanınıza danışın

[Bu bilgi mevcut kaynaklarda yer almamaktadır]"

KULLANICI SORUSU: {{ query }}""",
    max_tokens=500,
    temperature=0.1,
    requires_rag=False,
    citation_required=False,
    is_system_level=False,
    is_internal=True,
    jurisdiction=None,
)
