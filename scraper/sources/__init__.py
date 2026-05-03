from .coldwell import ColdwellBankerScraper
from .compass import CompassScraper
from .redfin import RedfinScraper
from .remax import RemaxScraper
from .century21 import Century21Scraper
from .bhhs import BHHSScraper
from .trulia import TruliaScraper
from .homesnap import HomesnapScraper
from .homes_com import HomesComScraper
from .point2 import Point2Scraper

ALL_SCRAPERS = [
    ColdwellBankerScraper,
    CompassScraper,
    RedfinScraper,
    RemaxScraper,
    Century21Scraper,
    BHHSScraper,
    TruliaScraper,
    HomesnapScraper,
    HomesComScraper,
    Point2Scraper,
]
