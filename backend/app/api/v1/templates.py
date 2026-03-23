from fastapi import APIRouter, Depends
from app.api.v1.deps import get_current_user
from app.models.user import User
from app.prompts.loader import prompt_registry

router = APIRouter()


@router.get("/")
async def list_templates(
    category: str | None = None,
    current_user: User = Depends(get_current_user),
):
    if category:
        templates = prompt_registry.list_by_category(category)
    else:
        templates = prompt_registry.list_all()

    return {
        "templates": [
            {
                "slug": t.slug,
                "category": t.category,
                "display_name_tr": t.display_name_tr,
                "display_name_en": t.display_name_en,
                "description_tr": t.description_tr,
                "requires_rag": t.requires_rag,
                "citation_required": t.citation_required,
                "billable": t.billable,
                "tags": t.tags,
            }
            for t in templates
        ]
    }


@router.get("/categories")
async def list_categories(current_user: User = Depends(get_current_user)):
    templates = prompt_registry.list_all()
    categories = list({t.category for t in templates})
    return {"categories": sorted(categories)}


@router.get("/{slug}")
async def get_template(slug: str, current_user: User = Depends(get_current_user)):
    template = prompt_registry.get(slug)
    return {
        "slug": template.slug,
        "category": template.category,
        "display_name_tr": template.display_name_tr,
        "display_name_en": template.display_name_en,
        "description_tr": template.description_tr,
        "tags": template.tags,
        "billable": template.billable,
    }
