from .generic import scrape_storefront
from .models import Result, Target


async def scrape(browser, target: Target, screenshot) -> Result:
    return await scrape_storefront(browser, target, screenshot)
