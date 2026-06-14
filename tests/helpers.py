# Plain factory helpers shared across the suite (kept out of conftest so they
# can be imported directly without relying on pytest's plugin machinery).
from typing import List, Optional

from src.state import Ingredient, ProductExtraction


def make_extraction(
    n_ingredients: int = 0,
    *,
    brand: str = "Test Brand",
    product_name: str = "Test Product",
    source_language: str = "JP",
    extraction_confidence: float = 0.9,
    system_status: str = "SUCCESS",
    ingredients: Optional[List[Ingredient]] = None,
    **overrides,
) -> ProductExtraction:
    """Build a ProductExtraction with `n_ingredients` placeholder ingredients.

    Pass an explicit `ingredients` list to override the placeholders.
    """
    if ingredients is None:
        ingredients = [
            Ingredient(name_raw=f"ing_{i}", source_language=source_language)
            for i in range(n_ingredients)
        ]
    return ProductExtraction(
        brand=brand,
        product_name=product_name,
        ingredients=ingredients,
        source_language=source_language,
        extraction_confidence=extraction_confidence,
        system_status=system_status,
        **overrides,
    )


def std_ingredients(*pairs) -> List[dict]:
    """Build a normalizer-shaped list from (name_raw, name_standardized) pairs.

    `name_standardized` may be None to represent an unmapped ingredient.
    """
    return [
        {
            "name_raw": raw,
            "name_standardized": inci,
            "is_active": None,
            "source_language": "JP",
        }
        for raw, inci in pairs
    ]
